#!/usr/bin/env python3
"""Persistent registry for AI Central sessions.

tmux panes disappear on a reboot, but conversation IDs do not.  This registry
is the small piece of durable state that lets the hub rebuild panes without
guessing which conversation belongs to a repository.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HOME = Path.home()
REGISTRY = Path(os.environ.get("AI_HUB_REGISTRY", HOME / ".config/ai-central/sessions.json"))

DEFAULT_SESSIONS = [
    {
        "name": "amaral-hub",
        "provider": "claude",
        "directory": "/var/www/amaral-intern-hub",
        "sessionId": "ab48b700-d36a-435f-b09b-8fcefb3262fb",
        "enabled": True,
    },
    {
        "name": "debthub",
        "provider": "claude",
        "directory": "/var/www/DEBTHUB-2.1",
        "sessionId": "b8e40305-2766-4b6b-8cea-3d755bb2a6cc",
        "enabled": True,
    },
    {
        "name": "adb-tools",
        "provider": "claude",
        "directory": "/var/www/adb_tools",
        "sessionId": "f02419e8-4cb9-4ba9-977b-d2bd8558b987",
        "enabled": True,
    },
    {
        "name": "home",
        "provider": "claude",
        "directory": str(HOME),
        "sessionId": "4ba7abc7-4b95-4cce-8a70-4f473c688337",
        "enabled": True,
    },
    {
        "name": "usage-widget",
        "provider": "claude",
        "directory": str(HOME / "claude-usage-widget"),
        "sessionId": "8e7adc74-7bdc-499d-9ce2-1eeaf7206327",
        "enabled": True,
    },
    {
        "name": "kubera-fe",
        "provider": "claude",
        "directory": "/var/www/kubera-fe",
        "sessionId": "ed77494d-7fd6-4a96-be82-c8ca8ef68591",
        "enabled": True,
    },
]


def _normalise(item: dict) -> dict | None:
    name = str(item.get("name") or "").strip()
    provider = str(item.get("provider") or "").strip().lower()
    directory = str(item.get("directory") or "").strip()
    if not name or provider not in {"claude", "codex"} or not directory:
        return None
    try:
        directory = str(Path(directory).expanduser().resolve())
    except OSError:
        directory = str(Path(directory).expanduser())
    return {
        "name": name,
        "provider": provider,
        "directory": directory,
        "sessionId": str(item.get("sessionId") or "").strip(),
        "enabled": bool(item.get("enabled", True)),
        "lastSeen": str(item.get("lastSeen") or ""),
    }


def load_registry() -> list[dict]:
    try:
        raw = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    sessions = raw.get("sessions", raw) if isinstance(raw, dict) else raw
    if not isinstance(sessions, list):
        return []
    return [normal for item in sessions if isinstance(item, dict) and (normal := _normalise(item))]


def save_registry(sessions: list[dict]) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {
        "version": 1,
        "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sessions": sessions,
    }
    temporary = REGISTRY.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, REGISTRY)


def seed_registry() -> list[dict]:
    sessions = load_registry()
    if sessions:
        return sessions
    sessions = [_normalise(item) for item in DEFAULT_SESSIONS]
    clean = [item for item in sessions if item]
    save_registry(clean)
    return clean


def upsert_session(item: dict, sessions: list[dict] | None = None) -> list[dict]:
    normal = _normalise(item)
    if not normal:
        raise ValueError("invalid session definition")
    current = list(sessions if sessions is not None else seed_registry())
    for position, existing in enumerate(current):
        if existing["name"] == normal["name"]:
            merged = {**existing, **normal}
            if not normal["sessionId"]:
                merged["sessionId"] = existing.get("sessionId", "")
            current[position] = merged
            break
    else:
        current.append(normal)
    save_registry(current)
    return current


def sync_snapshot(data: dict) -> list[dict]:
    sessions = seed_registry()
    changed = False
    by_name = {item["name"]: position for position, item in enumerate(sessions)}
    for live in data.get("sessions", []):
        if live.get("provider") not in {"claude", "codex"} or not live.get("sessionId"):
            continue
        item = _normalise(
            {
                "name": live.get("name"),
                "provider": live.get("provider"),
                "directory": live.get("directory"),
                "sessionId": live.get("sessionId"),
                "enabled": True,
                "lastSeen": data.get("generatedAt", ""),
            }
        )
        if not item:
            continue
        position = by_name.get(item["name"])
        if position is None:
            by_name[item["name"]] = len(sessions)
            sessions.append(item)
            changed = True
        elif sessions[position] != item:
            sessions[position] = item
            changed = True
    if changed:
        save_registry(sessions)
    return sessions


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("seed")
    subparsers.add_parser("show")
    sync = subparsers.add_parser("sync")
    sync.add_argument("snapshot", nargs="?", help="snapshot JSON; stdin when omitted")
    upsert = subparsers.add_parser("upsert")
    upsert.add_argument("name")
    upsert.add_argument("provider", choices=("claude", "codex"))
    upsert.add_argument("directory")
    upsert.add_argument("session_id", nargs="?", default="")
    args = parser.parse_args()

    if args.command == "seed":
        seed_registry()
    elif args.command == "show":
        print(json.dumps({"sessions": seed_registry()}, ensure_ascii=False, indent=2))
    elif args.command == "sync":
        raw = args.snapshot if args.snapshot is not None else sys.stdin.read()
        sync_snapshot(json.loads(raw))
    else:
        upsert_session(
            {
                "name": args.name,
                "provider": args.provider,
                "directory": args.directory,
                "sessionId": args.session_id,
                "enabled": True,
                "lastSeen": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
