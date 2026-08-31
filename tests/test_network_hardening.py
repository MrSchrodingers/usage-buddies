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


def _run_host_filter(codex, host, table, column, sql):
    """Run the collector's real host filter against a fixture row."""
    import sqlite3
    db = sqlite3.connect(":memory:")
    db.execute(f"CREATE TABLE {table} (name TEXT, value TEXT, {column} TEXT)")
    db.execute(f"INSERT INTO {table} VALUES ('s','v',?)", (host,))
    return bool(db.execute(sql, codex.CHATGPT_HOSTS).fetchall())


LOOKALIKES = [
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
    # Websocket host: carries nothing the usage endpoints need.
    ("ws.chatgpt.com", False),
]


@pytest.mark.parametrize("host,should_match", LOOKALIKES)
def test_codex_chromium_filter_rejects_lookalikes(codex, host, should_match):
    got = _run_host_filter(
        codex, host, "cookies", "host_key",
        "SELECT name FROM cookies WHERE host_key IN (?, ?)")
    assert got is should_match, f"{host!r} matched={got}, expected {should_match}"


@pytest.mark.parametrize("host,should_match", LOOKALIKES)
def test_codex_firefox_filter_rejects_lookalikes(codex, host, should_match):
    got = _run_host_filter(
        codex, host, "moz_cookies", "host",
        "SELECT name FROM moz_cookies WHERE host IN (?, ?)")
    assert got is should_match, f"{host!r} matched={got}, expected {should_match}"


def test_both_collectors_share_one_host_list(codex):
    """Chromium and Firefox paths must not drift apart on which hosts count.

    Asserting on the source text was tried and is worthless here: the word LIKE
    appears in the comment explaining why it is not used.
    """
    assert codex.CHATGPT_HOSTS == ("chatgpt.com", ".chatgpt.com")


def test_codex_reads_firefox(codex, monkeypatch, tmp_path):
    """Firefox stores cookies in plaintext and needs no keyring. Without this
    path a user logged into ChatGPT in Firefox gets an empty widget."""
    import sqlite3
    profile = tmp_path / ".mozilla" / "firefox" / "abc.default-release"
    profile.mkdir(parents=True)
    db = sqlite3.connect(profile / "cookies.sqlite")
    db.execute("CREATE TABLE moz_cookies (name TEXT, value TEXT, host TEXT)")
    db.execute("INSERT INTO moz_cookies VALUES ('__Secure-next-auth.session-token','tok','chatgpt.com')")
    db.execute("INSERT INTO moz_cookies VALUES ('other','x','.example.com')")
    db.commit(); db.close()

    monkeypatch.setattr(codex.Path, "home", staticmethod(lambda: tmp_path))
    got = codex.firefox_cookies()
    assert "__Secure-next-auth.session-token=tok" in got
    assert "other=x" not in got, "cookie from an unrelated host was collected"


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
