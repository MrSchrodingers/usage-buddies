"""Credentials must not leave the origin they belong to, or reach the journal.

Both collectors send a session cookie to a fixed JSON API. urllib follows
redirects by default and re-sends every header, so a 302 — from an open
redirect on the API host, or a proxy in the path — hands that cookie to
whatever host the Location names, over plain HTTP if it says so. And several
exceptions on this path quote the offending value in their message: ValueError
from an invalid header value quotes the whole cookie, BadStatusLine quotes the
server's raw bytes. Under systemd that message lands in the journal, every 30s.
"""
import http.server
import json
import re
import sys
import threading
import urllib.error
import urllib.request

import pytest


class _Sink(http.server.BaseHTTPRequestHandler):
    received = {}

    def do_GET(self):
        _Sink.received = {k.lower(): v for k, v in self.headers.items()}
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *a):
        pass


@pytest.fixture
def sink():
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Sink)
    _Sink.received = {}
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


@pytest.fixture
def redirector(sink):
    target = f"http://127.0.0.1:{sink.server_port}/stolen"

    class _Redir(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", target)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), _Redir)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


def test_plain_urlopen_leaks_the_cookie(sink, redirector):
    """Control: without the hardened opener the credential does leave. If this
    ever stops failing, urllib changed and the guard below proves nothing."""
    req = urllib.request.Request(f"http://127.0.0.1:{redirector.server_port}/usage",
                                 headers={"Cookie": "sessionKey=SECRET"})
    urllib.request.urlopen(req, timeout=5).read()
    assert _Sink.received.get("cookie") == "sessionKey=SECRET"


def test_hardened_opener_refuses_cross_origin_redirect(collector, sink, redirector):
    req = urllib.request.Request(f"http://127.0.0.1:{redirector.server_port}/usage",
                                 headers={"Cookie": "sessionKey=SECRET"})
    with pytest.raises(urllib.error.HTTPError):
        collector._OPENER.open(req, timeout=5)
    assert "cookie" not in _Sink.received, (
        f"credential reached the redirect target: {_Sink.received}"
    )


def test_same_origin_redirect_still_works(collector):
    """The guard must not break a legitimate redirect inside the same origin."""
    class _SelfRedir(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/usage":
                self.send_response(302)
                self.send_header("Location", "/usage/final")
                self.end_headers()
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), _SelfRedir)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_port}/usage")
        body = collector._OPENER.open(req, timeout=5).read()
        assert json.loads(body)["ok"] is True
    finally:
        srv.shutdown()


def test_cookie_with_control_bytes_cannot_reach_the_header(collector):
    """A cookie decrypted with the wrong key yields arbitrary bytes. Passing
    those to http.client raises ValueError quoting the entire cookie."""
    hostile = "sessionKey=SECRET\r\nX-Injected: 1"
    cleaned = collector._sanitize_header_value(hostile)
    assert "\r" not in cleaned and "\n" not in cleaned
    urllib.request.Request("https://example.invalid").add_header("Cookie", cleaned)


def test_api_request_reports_only_the_exception_class(collector, monkeypatch, capsys):
    """Failure output must never carry the cookie or the response body."""
    monkeypatch.setattr(collector, "get_claude_cookies", lambda: "sessionKey=SECRET")
    monkeypatch.setattr(collector, "get_org_id", lambda c: "org-123")

    def boom(*a, **k):
        raise ValueError("Invalid header value b'sessionKey=SECRET'")

    monkeypatch.setattr(collector._OPENER, "open", boom)
    assert collector._api_request("usage") is None
    err = capsys.readouterr().err
    assert "SECRET" not in err, f"credential printed on the failure path: {err}"
    assert "ValueError" in err


# ── Codex collector ──

@pytest.fixture
def codex():
    import importlib.util
    import sys
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "scripts" / "codex-usage-collector.py"
    spec = importlib.util.spec_from_file_location("codex_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["codex_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _cookie_sql(codex):
    """The SELECT the collector actually runs, pulled out of its source.

    Asserting on source text would be satisfied by a comment; this extracts the
    real statement and runs it, so the test fails if the filter changes.
    """
    import inspect
    src = inspect.getsource(codex.browser_cookies)
    m = re.search(r'database\.execute\(\s*((?:\s*"[^"]*"\s*)+)\)', src)
    assert m, f"could not locate the cookie query:\n{src}"
    return "".join(re.findall(r'"([^"]*)"', m.group(1)))


@pytest.mark.parametrize("host,should_match", [
    ("chatgpt.com", True),
    (".chatgpt.com", True),
    # A leading-wildcard LIKE matches all of these; they are attacker-controlled
    # domains a user may have visited once.
    ("evil-chatgpt.com.attacker.io", False),
    ("notopenai.com.evil.net", False),
    ("chatgpt.com.phish.ru", False),
    # Different registrable domain: the browser would never send chatgpt.com's
    # cookies here, or these to chatgpt.com.
    ("openai.com", False),
    (".openai.com", False),
])
def test_codex_cookie_query_rejects_lookalike_hosts(codex, host, should_match):
    import sqlite3
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE cookies (name TEXT, value TEXT, encrypted_value BLOB, host_key TEXT)")
    db.execute("INSERT INTO cookies VALUES ('s','v','', ?)", (host,))
    rows = db.execute(_cookie_sql(codex)).fetchall()
    assert bool(rows) is should_match, (
        f"{host!r} matched={bool(rows)}, expected {should_match}; query: {_cookie_sql(codex)}"
    )


def test_codex_recursion_is_bounded(codex):
    """Third-party JSON must not be able to raise RecursionError."""
    deep = {}
    node = deep
    for _ in range(5000):
        node["child"] = {}
        node = node["child"]
    assert codex.find_rate_limit_blocks(deep) == []


def test_codex_stays_quiet_without_verbose(codex, monkeypatch, capsys, tmp_path):
    """StandardOutput=journal, 2880 runs a day, and nothing consumes stdout."""
    monkeypatch.setattr(codex, "collect", lambda: {"rateLimits": {}, "plan": "secret-plan"})
    monkeypatch.setattr(codex, "DATA_DIR", tmp_path)
    monkeypatch.setattr(codex, "OUTPUT_FILE", tmp_path / "widget-data.json")
    monkeypatch.setattr(sys, "argv", ["codex-usage-collector.py"])
    codex.main()
    assert capsys.readouterr().out == "", "collector dumps its payload to the journal"


def test_codex_output_file_is_private(codex, monkeypatch, tmp_path):
    monkeypatch.setattr(codex, "collect", lambda: {"rateLimits": {}})
    monkeypatch.setattr(codex, "DATA_DIR", tmp_path / ".codex")
    monkeypatch.setattr(codex, "OUTPUT_FILE", tmp_path / ".codex" / "widget-data.json")
    monkeypatch.setattr(sys, "argv", ["codex-usage-collector.py"])
    codex.main()
    import stat
    mode = stat.S_IMODE((tmp_path / ".codex" / "widget-data.json").stat().st_mode)
    assert mode == 0o600, oct(mode)
    dir_mode = stat.S_IMODE((tmp_path / ".codex").stat().st_mode)
    assert dir_mode == 0o700, f"~/.codex is {oct(dir_mode)}; it also holds auth.json"
