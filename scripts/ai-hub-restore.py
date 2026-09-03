#!/usr/bin/env python3
"""Restore registered AI Central sessions after login without duplicates."""
from __future__ import annotations

import argparse
import fcntl
import os
import shlex
import subprocess
import time
from pathlib import Path

from ai_hub_registry import seed_registry

HOME = Path.home()
HUB = str(HOME / ".local/bin/claude-hub")
TMUX_SESSION = "claude-hub"
LOCK = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "ai-central-restore.lock"


def run(command: list[str], timeout: float = 8) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, text=True, capture_output=True, check=False, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return subprocess.CompletedProcess(command, 1, "", "")


def process_name(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/comm").read_text().strip()
    except OSError:
        return ""


def process_cwd(pid: int) -> str:
    try:
        return str(Path(f"/proc/{pid}/cwd").resolve())
    except OSError:
        return ""


def agent_processes_in(directory: str) -> list[tuple[int, str]]:
    matches = []
    try:
        expected = str(Path(directory).resolve())
    except OSError:
        expected = directory
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        name = process_name(pid)
        if name not in {"claude", "codex", "codex-cli"}:
            continue
        if process_cwd(pid) == expected:
            matches.append((pid, name))
    return matches


def window_state(name: str) -> tuple[str, str, str] | None:
    result = run(
        ["tmux", "display-message", "-p", "-t", f"{TMUX_SESSION}:{name}",
         "#{pane_current_path}\t#{pane_current_command}\t#{pane_dead}"],
        timeout=3,
    )
    if result.returncode != 0:
        return None
    fields = result.stdout.strip().split("\t")
    return tuple(fields) if len(fields) == 3 else None


def restore(dry_run: bool = False) -> list[str]:
    events = []
    if not dry_run:
        init = run([HUB, "init"], timeout=12)
        if init.returncode != 0:
            raise RuntimeError(init.stderr.strip() or "hub initialization failed")

    for item in seed_registry():
        if not item.get("enabled") or not item.get("sessionId"):
            continue
        name = item["name"]
        provider = item["provider"]
        directory = item["directory"]
        state = window_state(name)
        if state and state[1] in {"claude", "codex", "codex-cli"} and state[2] == "0":
            events.append(f"keep {name}: already live")
            continue
        conflicts = agent_processes_in(directory)
        if conflicts:
            pids = ",".join(str(pid) for pid, _ in conflicts)
            events.append(f"skip {name}: external agent in {directory} pid={pids}")
            continue
        if not Path(directory).is_dir():
            events.append(f"skip {name}: missing directory {directory}")
            continue

        if provider == "claude":
            command = ["claude", "--permission-mode", "bypassPermissions", "--resume", item["sessionId"]]
        else:
            command = ["codex", "resume", "--dangerously-bypass-approvals-and-sandbox", item["sessionId"]]
        events.append(f"restore {name}: {provider} {item['sessionId']}")
        if dry_run:
            continue
        if state is None:
            created = run(
                ["tmux", "new-window", "-d", "-t", f"={TMUX_SESSION}", "-n", name, "-c", directory,
                 "/usr/bin/zsh", "-l"],
                timeout=5,
            )
            if created.returncode != 0:
                events.append(f"error {name}: {created.stderr.strip()}")
                continue
        elif state[2] == "1":
            run(["tmux", "respawn-pane", "-k", "-t", f"{TMUX_SESSION}:{name}", "-c", directory,
                 "/usr/bin/zsh", "-l"], timeout=5)
        run(["tmux", "set-window-option", "-t", f"{TMUX_SESSION}:{name}", "aggressive-resize", "on"], timeout=3)
        command_text = shlex.join(command)
        run(["tmux", "send-keys", "-l", "-t", f"{TMUX_SESSION}:{name}", "--", command_text], timeout=3)
        run(["tmux", "send-keys", "-t", f"{TMUX_SESSION}:{name}", "Enter"], timeout=3)
        time.sleep(0.15)
    return events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        for event in restore(args.dry_run):
            print(event, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
