import importlib.util
import asyncio
import json
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "scripts" / "ai-central-web.py"


def load_server(tmp_path):
    spec = importlib.util.spec_from_file_location("ai_central_web_test", SERVER)
    module = importlib.util.module_from_spec(spec)
    sys.modules["ai_central_web_test"] = module
    spec.loader.exec_module(module)
    module.TOKEN_FILE = tmp_path / "token"
    return module


class FakeRequest:
    def __init__(self, token=""):
        self.headers = {"x-ai-token": token} if token else {}
        self.query_params = {}


class FakeWebSocket:
    def __init__(self, protocol=""):
        self.headers = {"sec-websocket-protocol": protocol}


def test_health_and_static_shell_are_available(tmp_path):
    server = load_server(tmp_path)
    assert asyncio.run(server.health()) == {"ok": True, "service": "ai-central"}
    page = asyncio.run(server.index())
    shell = Path(page.path).read_text()
    assert "AI Central" in shell
    assert 'id="keyboardButton"' in shell
    assert 'id="mobileKeyboard"' in shell
    assert 'data-sequence="keyboard"' in shell


def test_status_requires_constant_time_token_check(tmp_path, monkeypatch):
    server = load_server(tmp_path)
    monkeypatch.setattr(server, "state_payload", lambda *_args, **_kwargs: {"sessions": []})
    async def direct(function, *args):
        return function(*args)
    monkeypatch.setattr(server.asyncio, "to_thread", direct)
    token = server.access_token()
    with pytest.raises(HTTPException) as denied:
        asyncio.run(server.status(FakeRequest()))
    assert denied.value.status_code == 401
    response = asyncio.run(server.status(FakeRequest(token)))
    assert json.loads(response.body) == {"sessions": []}


def test_websocket_auth_uses_subprotocol_not_query_string(tmp_path):
    server = load_server(tmp_path)
    token = server.access_token()
    extracted, protocol = server.websocket_auth_protocol(FakeWebSocket(f"other, ai-central-auth.{token}"))
    assert extracted == token
    assert protocol == f"ai-central-auth.{token}"
    assert server.authorised(extracted)


def test_launch_rejects_missing_directory_before_invoking_hub(tmp_path, monkeypatch):
    server = load_server(tmp_path)
    token = server.access_token()
    invoked = []
    monkeypatch.setattr(server, "run", lambda *args, **kwargs: invoked.append(args))
    payload = server.LaunchRequest(mode="new", provider="codex", name="safe", directory=str(tmp_path / "missing"))
    with pytest.raises(HTTPException) as denied:
        asyncio.run(server.launch(payload, FakeRequest(token)))
    assert denied.value.status_code == 400
    assert not invoked


def test_status_reuses_the_monitor_cache(tmp_path, monkeypatch):
    server = load_server(tmp_path)
    token = server.access_token()
    cache = tmp_path / "state.json"
    cache.write_text(json.dumps({"sessions": [{"name": "cached"}]}))

    async def direct(function, *args):
        return function(*args)

    monkeypatch.setattr(server, "STATE_CACHE", cache)
    monkeypatch.setattr(server, "run", lambda *_args, **_kwargs: pytest.fail("fresh cache must avoid a subprocess"))
    monkeypatch.setattr(server.asyncio, "to_thread", direct)
    response = asyncio.run(server.status(FakeRequest(token)))
    assert json.loads(response.body) == {"sessions": [{"name": "cached"}]}
