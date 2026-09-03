import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def registry(tmp_path, monkeypatch):
    module = load_module("ai_hub_registry_test", SCRIPTS / "ai_hub_registry.py")
    monkeypatch.setattr(module, "REGISTRY", tmp_path / "config" / "sessions.json")
    monkeypatch.setattr(module, "DEFAULT_SESSIONS", [])
    return module


def test_registry_round_trip_and_permissions(registry, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    registry.upsert_session({"name": "api", "provider": "claude", "directory": str(repo), "sessionId": "abc", "enabled": True})

    assert registry.load_registry()[0]["sessionId"] == "abc"
    assert registry.REGISTRY.stat().st_mode & 0o777 == 0o600


def test_snapshot_updates_exact_resume_id(registry, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    registry.upsert_session({"name": "api", "provider": "codex", "directory": str(repo), "sessionId": "old", "enabled": True})
    registry.sync_snapshot({"generatedAt": "now", "sessions": [{"name": "api", "provider": "codex", "directory": str(repo), "sessionId": "new"}]})

    assert registry.load_registry()[0] == {
        "name": "api", "provider": "codex", "directory": str(repo), "sessionId": "new", "enabled": True, "lastSeen": "now"
    }


def test_invalid_provider_is_rejected(registry, tmp_path):
    with pytest.raises(ValueError):
        registry.upsert_session({"name": "bad", "provider": "shell", "directory": str(tmp_path)})


@pytest.fixture
def restore(monkeypatch):
    sys.path.insert(0, str(SCRIPTS))
    module = load_module("ai_hub_restore_test", SCRIPTS / "ai-hub-restore.py")
    yield module
    sys.path.remove(str(SCRIPTS))


def test_restore_dry_run_builds_resume_without_touching_tmux(restore, monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(restore, "seed_registry", lambda: [{"name": "api", "provider": "codex", "directory": str(repo), "sessionId": "thread-1", "enabled": True}])
    monkeypatch.setattr(restore, "window_state", lambda _name: (str(repo), "zsh", "0"))
    monkeypatch.setattr(restore, "agent_processes_in", lambda _directory: [])

    assert restore.restore(dry_run=True) == ["restore api: codex thread-1"]


def test_restore_refuses_external_writer(restore, monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(restore, "seed_registry", lambda: [{"name": "api", "provider": "claude", "directory": str(repo), "sessionId": "chat-1", "enabled": True}])
    monkeypatch.setattr(restore, "window_state", lambda _name: (str(repo), "zsh", "0"))
    monkeypatch.setattr(restore, "agent_processes_in", lambda _directory: [(42, "claude")])

    assert restore.restore(dry_run=True) == [f"skip api: external agent in {repo} pid=42"]
