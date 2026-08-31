#!/usr/bin/env python3
"""Collect Tollens harness state for the widget's second page.

Tollens governs the global Claude Code configuration: it keeps a versioned
manifest of ~/.claude, projects it into a root-owned managed scope that wins
the settings precedence chain, installs hooks, and compares installed against
versioned. Its thesis is INSTALLED != ENFORCED != ACTIVATED, and the page is
built to show those three separately rather than collapse them into one light.

Two layers, because they cost different amounts:

  A. Pure reads (~35ms) — presence, enforcement, the hook map, the manifest
     inventory. Every run.
  B. The real verifiers (~750ms total) — install/verify.sh and
     apply-managed.sh --verify. Throttled, because 0.75s against a 30s timer is
     2.5% of a core spent re-deriving something that changes rarely.

Deliberately NOT read:
  - ~/.claude/logs/subagent-probe.jsonl carries `last_assistant_message` and
    `cwd`; the file's own header says the payload must not leave the machine.
  - /var/log/tollens-activation.jsonl carries project file paths that name
    clients. Only an aggregate count would ever be safe, and it is not worth it.

The SessionStart heartbeat is read, but only ever reported as history with its
own timestamp attached. It is not current state: measured two hours stale with
a verdict inverted against a live run.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

MANAGED_SETTINGS = Path("/etc/claude-code/managed-settings.json")
TOLLENS_SRC = Path(os.environ.get("TOLLENS_REPO", "/opt/.tollens-src"))
HEARTBEAT = Path.home() / ".claude" / "evidence" / "session-integrity.jsonl"

# Outside ~/.claude on purpose: that tree is what Tollens audits, and a widget
# file sitting in it is a candidate orphan the moment their scan widens.
OUT_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "usage-buddies"
OUT_FILE = OUT_DIR / "tollens.json"

VERIFY_EVERY_SECONDS = 300
VERIFY_TIMEOUT = 20

# verify.sh names the failing scope in its exit code.
VERIFY_EXIT = {
    0: ("conformant", "installed matches the manifest"),
    1: ("user-drift", "user projection diverges from the manifest"),
    3: ("managed-missing", "managed policy is not deployed"),
    4: ("managed-writable", "managed policy is writable by the actor"),
    5: ("managed-drift", "managed policy diverges from the manifest"),
}


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def detect() -> dict:
    """Layer A. Presence and enforcement are different questions, so they get
    different fields: a policy can be installed and not enforced."""
    settings = _read_json(MANAGED_SETTINGS)
    if not settings or settings.get("_managed_by") != "tollens":
        return {"present": False}

    hooks = settings.get("hooks") or {}
    by_event = {}
    total = 0
    for event, entries in hooks.items():
        n = 0
        for entry in entries if isinstance(entries, list) else []:
            n += len(entry.get("hooks") or [])
        if n:
            by_event[event] = n
            total += n

    return {
        "present": True,
        "enforced": settings.get("allowManagedHooksOnly") is True,
        "hooks": {"total": total, "byEvent": by_event},
        "repo": str(TOLLENS_SRC),
    }


def inventory() -> dict:
    """Component counts from the versioned manifest — a TSV of
    type/source/destination/sha256."""
    manifest = TOLLENS_SRC / "install" / "manifest.lock"
    counts = {}
    try:
        with open(manifest, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 4 or not parts[0] or parts[0].startswith("#"):
                    continue
                counts[parts[0]] = counts.get(parts[0], 0) + 1
    except OSError:
        return {}
    return {"byType": counts, "total": sum(counts.values())}


def _run(cmd, cwd):
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                           timeout=VERIFY_TIMEOUT)
        return r.returncode, r.stdout
    except (OSError, subprocess.SubprocessError):
        return None, ""


def _summary_line(text, prefix):
    for line in text.splitlines():
        if line.startswith(prefix):
            return line.strip()
    return ""


def _numbers(line):
    """Pull the counters out of a summary line.

    verify.sh emits prose — "PROJECAO USUARIO: 39/49 ok | 10 divergentes | 0
    ausentes | 0 orfaos". Rendering that raw wraps badly in a narrow popup and
    forces one language on the widget. Parsing it here lets the page lay the
    numbers out and label them in whatever language is selected.
    """
    import re
    out = {}
    m = re.search(r"(\d+)\s*/\s*(\d+)\s*ok", line)
    if m:
        out["ok"], out["total"] = int(m.group(1)), int(m.group(2))
    for key, word in (("divergent", "divergent"), ("missing", "ausent"),
                      ("orphans", "orfao"), ("components", "componente"),
                      ("wrongOwner", "dono errado"), ("writable", "gravave")):
        # [^|]* rather than \S*: the counters are separated by pipes and the
        # words between number and label vary ("0 com dono errado").
        m = re.search(r"(\d+)[^|]*?" + word, line)
        if m:
            out[key] = int(m.group(1))
    return out


def conformance() -> dict:
    """Layer B. Both verifiers are read-only and need no root — established by
    snapshotting mtime and size across 6443 entries before and after."""
    started = time.monotonic()
    rc, out = _run(["bash", "install/verify.sh"], TOLLENS_SRC)
    if rc is None:
        return {"available": False}

    state, detail = VERIFY_EXIT.get(rc, ("unknown", f"verify exited {rc}"))
    result = {
        "available": True,
        "state": state,
        "detail": detail,
        "exitCode": rc,
        "user": _summary_line(out, "PROJECAO USUARIO:"),
        "userCounts": _numbers(_summary_line(out, "PROJECAO USUARIO:")),
        "checkedAt": time.time(),
    }

    mrc, mout = _run(["bash", "install/apply-managed.sh", "--verify"], TOLLENS_SRC)
    if mrc is not None:
        result["managed"] = _summary_line(mout, "managed:")
        result["managedCounts"] = _numbers(_summary_line(mout, "managed:"))
        result["managedExitCode"] = mrc

    result["tookSeconds"] = round(time.monotonic() - started, 3)
    return result


def heartbeat() -> dict:
    """Last SessionStart record. Reported as history, never as current state:
    it is written once per session start and was measured two hours stale with
    a verdict inverted against a live run. Old lines lack several fields."""
    try:
        last = ""
        with open(HEARTBEAT, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip():
                    last = line
        if not last:
            return {}
        rec = json.loads(last)
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        "at": rec.get("ts", ""),
        "result": rec.get("result", ""),
        "user": rec.get("summary", ""),
        "managed": rec.get("managed_summary", ""),
    }


def collect() -> dict:
    data = detect()
    if not data.get("present"):
        return data

    data["inventory"] = inventory()
    data["heartbeat"] = heartbeat()

    previous = _read_json(OUT_FILE) or {}
    prior = previous.get("conformance") or {}
    age = time.time() - (prior.get("checkedAt") or 0)
    if age >= VERIFY_EVERY_SECONDS or "--now" in sys.argv:
        data["conformance"] = conformance()
    else:
        data["conformance"] = prior

    # Tollens records no hook timings anywhere — searched evidence/, execution/,
    # control/ and orchestration/. Stated rather than left as an empty chart.
    data["notes"] = {"hookTimings": "not measured by Tollens"}
    data["generatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    return data


def main() -> None:
    try:
        data = collect()
    except Exception as error:
        print(f"error: tollens probe failed: {type(error).__name__}", file=sys.stderr)
        raise SystemExit(1) from None

    OUT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = OUT_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    os.chmod(tmp, 0o600)
    os.replace(tmp, OUT_FILE)

    if "--verbose" in sys.argv:
        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
