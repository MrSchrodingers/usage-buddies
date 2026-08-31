"""The Tollens probe reads a governed config; what it must NOT read matters most.

Two files in that tree carry data that must never reach a widget JSON:
subagent-probe.jsonl holds `last_assistant_message` and `cwd` (its own header
says the payload must not leave the machine), and the activation log holds
project file paths that name clients.
"""
import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / "scripts" / "tollens-probe.py"


@pytest.fixture
def probe(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("tollens_probe", PROBE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tollens_probe"] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(mod, "OUT_FILE", tmp_path / "out" / "tollens.json")
    return mod


def _settings(tmp_path, **over):
    d = {
        "_managed_by": "tollens",
        "allowManagedHooksOnly": True,
        "hooks": {
            "SessionStart": [{"hooks": [{"command": "a"}]}],
            "PreToolUse": [{"hooks": [{"command": "b"}, {"command": "c"}]}],
        },
    }
    d.update(over)
    p = tmp_path / "managed-settings.json"
    p.write_text(json.dumps(d))
    return p


# ── absence and identity ──

def test_absent_tollens_reports_only_absence(probe, monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "MANAGED_SETTINGS", tmp_path / "nope.json")
    assert probe.detect() == {"present": False}


def test_a_managed_settings_from_something_else_is_not_tollens(probe, monkeypatch, tmp_path):
    """The file existing is not the question; who owns it is."""
    monkeypatch.setattr(probe, "MANAGED_SETTINGS",
                        _settings(tmp_path, _managed_by="something-else"))
    assert probe.detect()["present"] is False


def test_present_and_enforced_are_separate_questions(probe, monkeypatch, tmp_path):
    """A policy can be deployed and not enforced. Collapsing the two into one
    light is exactly the confusion Tollens exists to name."""
    monkeypatch.setattr(probe, "MANAGED_SETTINGS",
                        _settings(tmp_path, allowManagedHooksOnly=False))
    got = probe.detect()
    assert got["present"] is True
    assert got["enforced"] is False


def test_hooks_are_counted_per_event(probe, monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "MANAGED_SETTINGS", _settings(tmp_path))
    hooks = probe.detect()["hooks"]
    assert hooks["total"] == 3
    assert hooks["byEvent"] == {"SessionStart": 1, "PreToolUse": 2}


# ── manifest ──

def test_inventory_counts_by_type(probe, monkeypatch, tmp_path):
    src = tmp_path / "src" / "install"
    src.mkdir(parents=True)
    (src / "manifest.lock").write_text(
        "hook\ta\tb\tsha1\n"
        "hook\tc\td\tsha2\n"
        "agent\te\tf\tsha3\n"
        "# comment line\n"
        "\n")
    monkeypatch.setattr(probe, "TOLLENS_SRC", tmp_path / "src")
    assert probe.inventory() == {"byType": {"hook": 2, "agent": 1}, "total": 3}


def test_missing_manifest_is_empty_not_a_crash(probe, monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "TOLLENS_SRC", tmp_path / "absent")
    assert probe.inventory() == {}


# ── heartbeat ──

def test_heartbeat_reads_the_last_line(probe, monkeypatch, tmp_path):
    hb = tmp_path / "hb.jsonl"
    hb.write_text(
        json.dumps({"ts": "old", "result": "ok"}) + "\n" +
        json.dumps({"ts": "2026-08-31T19:23:20Z", "result": "drift",
                    "summary": "PROJECAO USUARIO: 48/49 ok",
                    "managed_summary": "managed: 31 componentes"}) + "\n")
    monkeypatch.setattr(probe, "HEARTBEAT", hb)
    got = probe.heartbeat()
    assert got["at"] == "2026-08-31T19:23:20Z"
    assert got["result"] == "drift"


def test_heartbeat_tolerates_the_older_schema(probe, monkeypatch, tmp_path):
    """The first records predate several fields; a strict parser breaks on them."""
    hb = tmp_path / "hb.jsonl"
    hb.write_text(json.dumps({"ts": "2026-08-04T00:00:00Z", "policy": "user"}) + "\n")
    monkeypatch.setattr(probe, "HEARTBEAT", hb)
    got = probe.heartbeat()
    assert got["at"] == "2026-08-04T00:00:00Z"
    assert got["user"] == "" and got["managed"] == ""


def test_missing_heartbeat_is_empty(probe, monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "HEARTBEAT", tmp_path / "absent.jsonl")
    assert probe.heartbeat() == {}


# ── privacy ──

SENSITIVE = ["subagent-probe", "activation-log", "tollens-activation",
             "last_assistant_message", "transcript_path"]


@pytest.mark.parametrize("needle", SENSITIVE)
def test_probe_never_names_a_sensitive_source(needle):
    """subagent-probe.jsonl carries `last_assistant_message` and `cwd`; the
    activation log carries project paths that name clients. Neither belongs in
    a JSON a desktop widget reads."""
    body = PROBE.read_text()
    code = "\n".join(l for l in body.split("\n") if not l.strip().startswith("#"))
    # the docstring names them to explain the exclusion; code must not
    code = code.split('"""', 2)[-1]
    assert needle not in code, f"probe references {needle!r} outside its rationale"


def test_output_lands_outside_the_audited_tree():
    """~/.claude is what Tollens audits. A widget file inside it is a candidate
    orphan the moment their scan widens."""
    body = PROBE.read_text()
    assert 'OUT_DIR' in body and 'XDG_CACHE_HOME' in body
    assert '.claude" / "usage-buddies' not in body


# ── output ──

def test_written_file_is_private(probe, monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "MANAGED_SETTINGS", tmp_path / "nope.json")
    monkeypatch.setattr(sys, "argv", ["tollens-probe.py"])
    probe.main()
    mode = stat.S_IMODE(probe.OUT_FILE.stat().st_mode)
    assert mode == 0o600, oct(mode)
    assert json.loads(probe.OUT_FILE.read_text()) == {"present": False}


def test_conformance_is_throttled(probe, monkeypatch, tmp_path):
    """0.75s against a 30s timer is 2.5% of a core spent re-deriving something
    that changes rarely."""
    monkeypatch.setattr(probe, "MANAGED_SETTINGS", _settings(tmp_path))
    monkeypatch.setattr(probe, "TOLLENS_SRC", tmp_path / "absent")
    calls = []
    monkeypatch.setattr(probe, "conformance",
                        lambda: calls.append(1) or {"available": True,
                                                    "checkedAt": probe.time.time()})
    monkeypatch.setattr(sys, "argv", ["tollens-probe.py"])
    probe.main()
    probe.main()
    probe.main()
    assert len(calls) == 1, f"conformance ran {len(calls)} times in a row"


def test_probe_runs_end_to_end(tmp_path):
    """It must not crash on this machine, whatever Tollens' state is."""
    env = {**dict(__import__("os").environ), "XDG_CACHE_HOME": str(tmp_path)}
    r = subprocess.run([sys.executable, str(PROBE)], capture_output=True,
                       text=True, timeout=60, env=env)
    assert r.returncode == 0, r.stderr
    out = json.loads((tmp_path / "usage-buddies" / "tollens.json").read_text())
    assert "present" in out
