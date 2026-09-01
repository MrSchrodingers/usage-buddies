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
    # Both axes: a companion that only slides along one line is a status bar
    # with a face.
    assert out["movedX"] > 10, f"barely moved horizontally: {out}"
    assert out["movedY"] > 10, f"never left the bottom line: {out}"
    x, y, w, h = out["geometry"]
    assert w > 0 and h > 0


# ── movement, docking and the click/drag distinction ──

def _companion(monkeypatch):
    """A Companion with its polling neutralised, so tests drive it."""
    import os as _os
    _os.environ["QT_QPA_PLATFORM"] = "xcb"
    spec = importlib.util.spec_from_file_location("companion_ui", COMPANION)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["companion_ui"] = mod
    spec.loader.exec_module(mod)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    c = mod.Companion()
    c.poll_timer.stop()
    c._poll = lambda: None
    return mod, app, c


needs_display = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None or not os.environ.get("DISPLAY"),
    reason="PySide6 or X display missing")


@needs_display
def test_it_leaves_the_bottom_line(monkeypatch):
    """A companion confined to one line is a status bar with a face."""
    mod, app, c = _companion(monkeypatch)
    ys = {c._pick_target()[1] for _ in range(60)}
    assert len(ys) > 20, "targets cluster on one line"
    assert min(ys) < c.min_y + (c.max_y - c.min_y) * 0.5, "never goes above mid-screen"


@needs_display
def test_targets_favour_the_lower_half(monkeypatch):
    """Uniform placement puts it over whatever is being read as often as not."""
    mod, app, c = _companion(monkeypatch)
    span = c.max_y - c.min_y
    ys = [c._pick_target()[1] for _ in range(400)]
    lower = sum(1 for y in ys if y > c.min_y + span / 2)
    assert lower / len(ys) > 0.6, f"only {lower / len(ys):.0%} in the lower half"


@needs_display
def test_frame_rate_drops_when_it_settles(monkeypatch):
    """30fps to animate a character that is standing still is a steady slice of
    a core for nothing."""
    mod, app, c = _companion(monkeypatch)
    c.target = (c.pos_x, c.pos_y)
    c.next_move = float("inf")
    c.docked = False
    c.click_at = 0
    c._tick()
    assert c.frame_timer.interval() == mod.FRAME_MS_IDLE
    c.target = (c.min_x, c.min_y)
    c._tick()
    assert c.frame_timer.interval() == mod.FRAME_MS_ACTIVE


@needs_display
def test_dropped_in_a_corner_it_stays(monkeypatch):
    """Putting something in a corner is an instruction; wandering off ignores it."""
    mod, app, c = _companion(monkeypatch)
    c.pos_x, c.pos_y = float(c.min_x + 2), float(c.min_y + 2)
    c._snap()
    assert c.docked is True
    assert (c.pos_x, c.pos_y) == (float(c.min_x), float(c.min_y))
    # and it does not pick a new target while docked
    before = c.target
    c.next_move = 0
    c._tick()
    assert c.target == before


@needs_display
def test_dropped_mid_screen_it_resumes_roaming(monkeypatch):
    mod, app, c = _companion(monkeypatch)
    c.pos_x = float((c.min_x + c.max_x) / 2)
    c.pos_y = float((c.min_y + c.max_y) / 2)
    c._snap()
    assert c.docked is False


@needs_display
def test_undock_lets_it_roam_again(monkeypatch):
    mod, app, c = _companion(monkeypatch)
    c.docked = True
    c._undock()
    assert c.docked is False


@needs_display
def test_a_click_falls_back_to_some_session(monkeypatch):
    """A click that silently does nothing reads as broken, and there is always
    a session worth jumping to."""
    mod, app, c = _companion(monkeypatch)
    c.brain.sessions = {"attention": None,
                        "sessions": [{"pid": 4242, "name": "repo", "state": "working"}]}
    called = []
    monkeypatch.setattr(mod.subprocess, "Popen",
                        lambda cmd, **kw: called.append(cmd))
    monkeypatch.setattr(mod, "FOCUS_HELPER", Path("/bin/true"))
    c._go_to_session()
    assert called and called[0][-1] == "4242", called


@needs_display
def test_a_session_needing_attention_wins_the_click(monkeypatch):
    mod, app, c = _companion(monkeypatch)
    c.brain.sessions = {"attention": {"pid": 111, "name": "hub", "state": "waiting"},
                        "sessions": [{"pid": 222, "name": "other", "state": "working"}]}
    called = []
    monkeypatch.setattr(mod.subprocess, "Popen", lambda cmd, **kw: called.append(cmd))
    monkeypatch.setattr(mod, "FOCUS_HELPER", Path("/bin/true"))
    c._go_to_session()
    assert called[0][-1] == "111"


@needs_display
def test_the_window_accepts_mouse_input(monkeypatch):
    """BypassWindowManagerHint is unnecessary for positioning under XWayland —
    both variants were measured placing and moving a window — and it costs
    reliable mouse input, which click and drag need.

    Checked on the live window flags, not the source: the source mentions the
    hint in the comment explaining why it is absent, which an earlier version
    of this test happily matched.
    """
    from PySide6.QtCore import Qt
    mod, app, c = _companion(monkeypatch)
    flags = c.windowFlags()
    assert not (flags & Qt.BypassWindowManagerHint), "input would be unreliable"
    assert flags & Qt.WindowStaysOnTopHint, "would sink behind other windows"
    assert flags & Qt.FramelessWindowHint
