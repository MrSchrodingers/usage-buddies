"""Regression tests for the shared Claude/Codex lifecycle vocabulary."""

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "scripts" / "ai-hub-state.py"


@pytest.fixture
def hub(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("ai_hub_state", HELPER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ai_hub_state"] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "CODEX_ROLLOUTS", tmp_path / "rollouts")
    monkeypatch.setattr(mod, "NOTIFY_STATE", tmp_path / "notify-state.json")
    return mod


def _timestamp(seconds_ago=0):
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


def _rollout(hub, tmp_path, *records):
    directory = tmp_path / "repo"
    directory.mkdir()
    target = hub.CODEX_ROLLOUTS / "2026" / "09" / "session.jsonl"
    target.parent.mkdir(parents=True)
    all_records = [
        {"timestamp": _timestamp(60), "type": "session_meta", "payload": {"id": "codex-session", "cwd": str(directory)}}
    ]
    all_records.extend(records)
    target.write_text("".join(json.dumps(record) + "\n" for record in all_records))
    return directory


def test_codex_task_started_means_working_even_after_an_old_completion(hub, tmp_path):
    directory = _rollout(
        hub,
        tmp_path,
        {"timestamp": _timestamp(50), "type": "event_msg", "payload": {"type": "task_complete"}},
        {"timestamp": _timestamp(5), "type": "event_msg", "payload": {"type": "task_started"}},
    )
    assert hub.codex_state(str(directory), 0) == ("working", "Turno ou workflow em execução", "codex-session")


def test_codex_completion_waits_for_the_continuation_window(hub, tmp_path):
    directory = _rollout(
        hub,
        tmp_path,
        {"timestamp": _timestamp(2), "type": "event_msg", "payload": {"type": "task_complete"}},
    )
    assert hub.codex_state(str(directory), 0)[0] == "finalizing"


def test_codex_settled_completion_is_finished(hub, tmp_path):
    directory = _rollout(
        hub,
        tmp_path,
        {"timestamp": _timestamp(45), "type": "event_msg", "payload": {"type": "task_complete"}},
    )
    assert hub.codex_state(str(directory), 0)[0] == "finished"


def test_unanswered_codex_question_outranks_lifecycle(hub, tmp_path):
    directory = _rollout(
        hub,
        tmp_path,
        {"timestamp": _timestamp(45), "type": "event_msg", "payload": {"type": "task_complete"}},
        {"timestamp": _timestamp(2), "type": "response_item", "payload": {"type": "function_call", "name": "request_user_input", "call_id": "q1"}},
    )
    assert hub.codex_state(str(directory), 0)[0] == "asking"


def test_active_shell_descendant_keeps_background_work_visible(hub, monkeypatch):
    tree = {100: [101], 101: [102], 102: []}
    monkeypatch.setattr(hub, "process_children", lambda pid: tree.get(pid, []))
    monkeypatch.setattr(hub, "process_name", lambda pid: {101: "node", 102: "bash"}.get(pid, ""))
    assert hub.active_shell_descendant(100) == 102


def test_codex_completion_notification_fires_once_after_initialization(hub, monkeypatch):
    fired = []
    monkeypatch.setattr(hub, "send_notification", lambda *args: fired.append(args))

    def data(state, provider="codex"):
        return {"sessions": [{"name": "api", "provider": provider, "state": state, "directory": "/repo"}]}

    hub.notify_transitions(data("working"))
    hub.notify_transitions(data("finished"))
    hub.notify_transitions(data("finished"))
    hub.notify_transitions(data("waiting", provider="claude"))

    assert len(fired) == 1
    assert "finalizado" in fired[0][0]


def test_new_session_and_idle_transition_are_announced(hub, monkeypatch):
    fired = []
    monkeypatch.setattr(hub, "send_notification", lambda *args: fired.append(args))

    def data(sessions):
        return {"sessions": sessions}

    original = {"name": "one", "provider": "claude", "state": "working", "directory": "/one"}
    added = {"name": "two", "provider": "codex", "state": "working", "directory": "/two"}
    hub.notify_transitions(data([original]))
    hub.notify_transitions(data([original, added]))
    hub.notify_transitions(data([{**original, "state": "idle"}, added]))

    assert [call[0].split(": ")[-1] for call in fired] == ["conectado", "parado"]


def test_snapshot_cache_is_atomic_private_and_age_limited(hub, monkeypatch, tmp_path):
    cache = tmp_path / "cache" / "state.json"
    monkeypatch.setattr(hub, "STATE_CACHE", cache)
    payload = {"sessions": [{"name": "api"}], "updated": "now"}

    hub.write_snapshot_cache(payload)

    assert hub.cached_snapshot(15) == payload
    assert cache.stat().st_mode & 0o777 == 0o600
    monkeypatch.setattr(hub.time, "time", lambda: cache.stat().st_mtime + 20)
    assert hub.cached_snapshot(15) is None
