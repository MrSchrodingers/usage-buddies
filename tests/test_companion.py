"""The desktop companion, and the two traps in controlling it.

It is a separate process because a Plasma applet lives inside the panel's
window and cannot wander the screen; and it runs under XWayland because Wayland
has no call for a client to position its own window.
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
COMPANION = REPO / "scripts" / "usage-buddy-companion.py"
CTL = REPO / "scripts" / "companion-ctl.sh"


def _brain(**over):
    """The decision half, loaded without starting Qt."""
    spec = importlib.util.spec_from_file_location("companion_mod", COMPANION)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["companion_mod"] = mod
    spec.loader.exec_module(mod)
    b = mod.Brain(over.pop("lang", "en"), over.pop("alerts_only", False))
    b.sessions = over.pop("sessions", {})
    b.usage = over.pop("usage", {})
    return b


@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 missing")
def test_a_session_asking_outranks_everything(_qt_env=None):
    b = _brain(sessions={"attention": {"state": "asking", "name": "hub", "idleSeconds": 5}},
               usage={"compaction": {"count": 99}})
    assert "hub" in b.line()


@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 missing")
def test_alerts_only_stays_quiet_about_jokes():
    """The mode worth leaving on speaks solely when a session needs the human."""
    b = _brain(alerts_only=True,
               usage={"compaction": {"count": 99},
                      "efficiency": {"readPerOutput": 900, "cacheHitRate": 0.1}})
    assert b.line() is None


@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 missing")
def test_alerts_only_still_reports_a_waiting_session():
    b = _brain(alerts_only=True,
               sessions={"attention": {"state": "waiting", "name": "hub", "idleSeconds": 120}})
    assert "hub" in b.line()


@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 missing")
def test_nothing_to_report_is_silence():
    """What ruined Clippy was speaking with nothing to say."""
    b = _brain(sessions={"sessions": [], "attention": None},
               usage={"compaction": {"count": 0},
                      "efficiency": {"readPerOutput": 5, "cacheHitRate": 0.9},
                      "toolUse": {"byTool": {"Bash": 10, "Read": 10}}})
    import time
    if 0 <= time.localtime().tm_hour < 5:
        pytest.skip("the night-owl line is legitimately due at this hour")
    assert b.line() is None


@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 missing")
def test_lines_exist_in_both_languages():
    spec = importlib.util.spec_from_file_location("companion_mod2", COMPANION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    en, pt = mod.LINES["en"], mod.LINES["pt"]
    assert set(en) == set(pt), set(en) ^ set(pt)
    for key in en:
        assert en[key] and pt[key], key


# ── the control script: two real traps ──

def test_ctl_does_not_kill_its_own_shell():
    """`pkill -f usage-buddy-companion` kills the shell running it, because
    that string is in its own command line. This happened."""
    r = subprocess.run(["bash", str(CTL), "stop"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert r.stderr.strip() == "", f"noise on stderr: {r.stderr}"


def test_ctl_matches_the_script_behind_the_interpreter():
    """A shebang script is exec'd as `/usr/bin/python3 /path/script.py`, so
    argv[0] is the interpreter. Matching only argv[0] counts nothing."""
    body = CTL.read_text()
    assert "head -2" in body, "only the first argv entry is inspected"
    assert 'SELF=$$' in body and '[ "$p" = "$SELF" ]' in body, "does not skip itself"


def test_ctl_status_is_a_number():
    r = subprocess.run(["bash", str(CTL), "status"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().isdigit(), r.stdout


def test_ctl_rejects_an_unknown_verb():
    r = subprocess.run(["bash", str(CTL), "wat"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 2


@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 missing")
@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="no X display")
def test_companion_actually_moves():
    """Its whole point is wandering. --self-test walks it and reports how far."""
    r = subprocess.run([sys.executable, str(COMPANION), "--self-test"],
                       capture_output=True, text=True, timeout=60,
                       env={**os.environ, "QT_QPA_PLATFORM": "xcb"})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["moved"] > 10, f"barely moved: {out}"
    x, y, w, h = out["geometry"]
    assert w > 0 and h > 0
