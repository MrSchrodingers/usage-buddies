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
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
COMPANION = REPO / "scripts" / "usage-buddy-companion.py"
CTL = REPO / "scripts" / "companion-ctl.sh"

sys.path.insert(0, str(REPO / "scripts"))
import buddy_peers as peers                                          # noqa: E402

# Noon, local, on a fixed date. Some of what the companion says depends on the
# hour of day, and a suite whose result depends on when it is run is a suite
# nobody trusts the failures of.
_MIDDAY = time.mktime((2026, 9, 2, 12, 0, 0, 2, 245, -1))


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
    """Blocked on a question beats every diagnostic, however loud."""
    b = _brain(sessions={"sessions": [{"state": "asking", "name": "hub", "idleSeconds": 5}],
                         "attention": None, "total": 1},
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
               sessions={"sessions": [{"state": "waiting", "name": "hub", "idleSeconds": 120}],
                         "attention": None, "total": 1})
    assert "hub" in b.line()


@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 missing")
def test_alerts_only_says_nothing_when_nothing_is_wrong():
    """Silence is the default in the mode meant to be left on. In chatty mode a
    quiet system now gets ambient lines instead — going mute reads as broken,
    which is a different failure from being noisy."""
    b = _brain(alerts_only=True,
               sessions={"sessions": [], "attention": None, "total": 0},
               usage={"compaction": {"count": 0},
                      "efficiency": {"readPerOutput": 5, "cacheHitRate": 0.9},
                      "toolUse": {"byTool": {"Bash": 10, "Read": 10}}})
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

def _fake_proc(root, entries):
    """A /proc with the given {pid: argv-bytes}, for the ctl to scan."""
    for pid, argv in entries.items():
        (root / str(pid)).mkdir(parents=True)
        (root / str(pid) / "cmdline").write_bytes(argv)
    return {"USAGE_BUDDY_PROC": str(root)}


def _ctl(verb, env=None):
    return subprocess.run(["bash", str(CTL), verb], capture_output=True, text=True,
                          timeout=30, env={**os.environ, **(env or {})})


def test_ctl_does_not_kill_its_own_shell(tmp_path):
    """`pkill -f usage-buddy-companion` kills the shell running it, because
    that string is in its own command line. This happened.

    Scanned against a directory this test built rather than against the real
    /proc. The previous version called `stop` for real: it asserted the right
    thing, passed, and killed whatever companion the user had running — proven
    by starting one, running this test, and counting zero afterwards. A suite
    that reaches out and stops the program it is testing is a suite nobody can
    run while using the program.
    """
    env = _fake_proc(tmp_path, {})
    r = _ctl("stop", env)
    assert r.returncode == 0, r.stderr
    assert r.stderr.strip() == "", f"noise on stderr: {r.stderr}"


def test_ctl_stops_a_companion_it_finds_and_leaves_everything_else(tmp_path):
    """The kill path itself, end to end, without touching a real companion.

    Two processes are started and only one is described to the ctl as a
    companion. A scan that matched too widely would take both; one that
    matched too narrowly would take neither.
    """
    mine = subprocess.Popen(["sleep", "120"])
    other = subprocess.Popen(["sleep", "120"])
    try:
        env = _fake_proc(tmp_path, {
            mine.pid: b"/usr/bin/python3\x00/home/u/.local/bin/usage-buddy-companion.py\x00",
            other.pid: b"/usr/bin/sleep\x00120\x00",
        })
        assert _ctl("status", env).stdout.strip() == "1"
        assert _ctl("stop", env).returncode == 0
        mine.wait(timeout=10)
        assert mine.returncode is not None, "the companion survived stop"
        assert other.poll() is None, "stop killed a process that was not a companion"
    finally:
        for p in (mine, other):
            p.kill()
            p.wait(timeout=10)


def test_ctl_matches_the_script_behind_the_interpreter():
    """A shebang script is exec'd as `/usr/bin/python3 /path/script.py`, so
    argv[0] is the interpreter. Matching only argv[0] counts nothing."""
    body = CTL.read_text()
    assert "head -2" in body, "only the first argv entry is inspected"
    assert 'SELF=$$' in body and '[ "$p" = "$SELF" ]' in body, "does not skip itself"


# Command lines, and whether whoever ran each one is a companion this may kill.
#
# The two positives are the two shapes a companion actually starts in. The
# negatives are all the same mistake — matching the script name anywhere in the
# command line — and the second of them is the expensive one: that is
# install.sh:299 copying the script into ~/.local/bin, so a `stop` while it ran
# sent SIGTERM to the `cp` and truncated the file being installed. This work
# multiplied the chances of hitting it by six, because main.qml now calls
# syncCompanion() from six handlers and `start` stops first.
#
# Position alone cannot separate them: `vim scripts/usage-buddy-companion.py`
# puts the name in argv[1] exactly where the interpreter does. The rule is who
# is running it — the script as its own argv[0], or an interpreter with the
# script as argv[1].
CTL_CASES = [
    ("the script as its own argv[0]",
     b"/home/u/.local/bin/usage-buddy-companion.py\x00--lang\x00en\x00", True),
    ("python3 running the script",
     b"/usr/bin/python3\x00/home/u/.local/bin/usage-buddy-companion.py\x00", True),
    ("a point-release python running the script",
     b"/usr/bin/python3.14\x00/home/u/.local/bin/usage-buddy-companion.py\x00", True),
    ("the other interpreter family",
     b"/usr/bin/pypy3\x00/home/u/.local/bin/usage-buddy-companion.py\x00", True),
    # The one the two implementations used to disagree about. The shell matched
    # a list of globs per version shape and had no entry for a two-digit point
    # release, so a companion under it survived `stop` and the next `start`
    # left two of them running. Both strip digits and dots and compare the
    # stem now, which is why the case below has to stay too: stripping without
    # comparing the whole stem would let anything that begins with the name
    # through.
    ("a two-digit point release of the other family",
     b"/usr/bin/pypy3.10\x00/home/u/.local/bin/usage-buddy-companion.py\x00", True),
    ("something whose name merely starts like an interpreter",
     b"/usr/bin/python3xyz\x00/home/u/.local/bin/usage-buddy-companion.py\x00", False),
    ("an editor with the file open",
     b"/usr/bin/vim\x00scripts/usage-buddy-companion.py\x00", False),
    ("the installer copying the script into place",
     b"/usr/bin/cp\x00scripts/usage-buddy-companion.py\x00/home/u/.local/bin/\x00", False),
    ("a shell that merely names it",
     b"/bin/sh\x00-c\x00echo usage-buddy-companion.py\x00", False),
    ("an interpreter running something else entirely",
     b"/usr/bin/python3\x00/home/u/other.py\x00usage-buddy-companion.py\x00", False),
]

# Above /proc/sys/kernel/pid_max (4194304 here), so no fake pid can collide
# with the ctl's own $$, which it skips by number. A collision would make a
# negative case pass for the wrong reason and nothing would say so.
_FAKE_PID = 9_000_001


@pytest.mark.parametrize("name,argv,expected", CTL_CASES,
                         ids=[case[0] for case in CTL_CASES])
def test_the_ctl_and_the_liveness_check_agree_on_who_is_running_the_script(
        name, argv, expected, tmp_path):
    """One table, both implementations of the same rule.

    companion-ctl.sh decides what `stop` kills and buddy_peers.is_companion
    decides which presence files are still a live companion. They were written
    apart and disagreed: the shell matched the name as a substring, so it
    answered yes to the editor and to the installer. Checking both against the
    same cases is what keeps the shell copy from drifting again.
    """
    env = _fake_proc(tmp_path, {_FAKE_PID: argv})
    counted = _ctl("status", env)
    assert counted.returncode == 0, counted.stderr
    assert counted.stdout.strip() == ("1" if expected else "0"), \
        f"companion-ctl.sh: {name} -> {counted.stdout.strip()}"
    assert peers.is_companion(_FAKE_PID, proc=str(tmp_path)) is expected, \
        f"buddy_peers.is_companion: {name}"


def test_stop_during_an_install_leaves_the_installer_alone(tmp_path):
    """The measured version of the case above, with processes that can die.

    Three of them, described to the ctl as the editor, the installer and the
    real companion. Before the fix `companion_pids` returned all three; the
    second is `cp` writing ~/.local/bin/usage-buddy-companion.py, so a `stop`
    at that moment truncated the file it was installing.
    """
    editor, installer, real = (subprocess.Popen(["sleep", "120"]) for _ in range(3))
    try:
        env = _fake_proc(tmp_path, {
            editor.pid: b"/usr/bin/vim\x00scripts/usage-buddy-companion.py\x00",
            installer.pid: (b"/usr/bin/cp\x00scripts/usage-buddy-companion.py"
                            b"\x00/home/u/.local/bin/\x00"),
            real.pid: (b"/usr/bin/python3\x00"
                       b"/home/u/.local/bin/usage-buddy-companion.py\x00"),
        })
        assert _ctl("status", env).stdout.strip() == "1"
        assert _ctl("stop", env).returncode == 0
        real.wait(timeout=10)
        assert real.returncode is not None, "the companion survived stop"
        assert editor.poll() is None, "stop killed the editor"
        assert installer.poll() is None, "stop killed the installer mid-copy"
    finally:
        for p in (editor, installer, real):
            p.kill()
            p.wait(timeout=10)


def test_ctl_status_is_a_number():
    r = subprocess.run(["bash", str(CTL), "status"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().isdigit(), r.stdout


def test_ctl_status_does_not_report_failure_because_of_who_else_is_running(tmp_path):
    """The count and the exit code have to agree, whatever /proc holds.

    The scan ends in a `[ ... ] &&` that fails for any interpreter running some
    other script, and a function inherits the status of its last iteration —
    so under `pipefail` the answer depended on which pid the glob visited last.
    The two entries here are a real companion and a `python3 -m pytest`, and
    the second sorts after the first: the count was right and the exit code was
    1, which is the test suite's own process making the ctl report failure.
    """
    env = _fake_proc(tmp_path, {
        _FAKE_PID: (b"/usr/bin/python3\x00"
                    b"/home/u/.local/bin/usage-buddy-companion.py\x00"),
        _FAKE_PID + 1: b"/usr/bin/python3\x00-m\x00pytest\x00",
    })
    r = _ctl("status", env)
    assert r.stdout.strip() == "1"
    assert r.returncode == 0, "counted correctly and reported failure anyway"


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


# ── variety: the complaint was "it keeps saying the same thing" ──

def _brain_with(sessions, usage=None, lang="en", alerts_only=False):
    spec = importlib.util.spec_from_file_location("companion_var", COMPANION)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["companion_var"] = mod
    spec.loader.exec_module(mod)
    b = mod.Brain(lang, alerts_only)
    b.sessions = sessions
    b.usage = usage or {}
    return mod, b


@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 missing")
def test_it_does_not_repeat_a_line_immediately():
    """Two lines in rotation is one line. The previous version said the same
    sentence about the same session for an hour."""
    mod, b = _brain_with({"sessions": [{"name": "ti", "state": "waiting", "idleSeconds": 300}],
                          "attention": None, "total": 1})
    said = [b.line() for _ in range(6)]
    assert len(set(said)) >= 5, said


@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 missing")
def test_it_rotates_between_sessions():
    """With three sessions waiting, always announcing the first turns a signal
    into background noise about one repo."""
    sessions = [{"name": n, "state": "waiting", "idleSeconds": 120}
                for n in ("alpha", "beta", "gamma")]
    mod, b = _brain_with({"sessions": sessions, "attention": None, "total": 3})
    said = [b.line() for _ in range(15)]
    named = {n for n in ("alpha", "beta", "gamma")
             if any(n in line for line in said)}
    assert named == {"alpha", "beta", "gamma"}, named


@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 missing")
def test_a_quiet_system_still_has_things_to_say():
    """With no alerts the old version went mute, which reads as broken."""
    mod, b = _brain_with(
        {"sessions": [{"name": "x", "state": "working"}], "attention": None, "total": 1},
        {"efficiency": {"cacheHitRate": 0.9, "readPerOutput": 5},
         "compaction": {"count": 0},
         "toolUse": {"byTool": {"Bash": 10, "Read": 10}}})
    # At a fixed hour of the working day. Left on the real clock this failed
    # between midnight and five in the morning and only then: the night-owl
    # remark is true for every draw in that window and its table holds four
    # lines, so the variety being asked for here cannot exist. Measured
    # against the committed version too — the hour has always decided it, and
    # a test that fails at 3am and passes at 3pm teaches everyone to re-run
    # the suite instead of reading it.
    said = [b.line(wall=_MIDDAY) for _ in range(8)]
    assert all(said), "went silent with nothing wrong"
    # Not 8: the quiet categories hold seven and six lines, and the
    # no-repeats window is shared between them, so the eighth draw can be
    # forced to reuse one. Asking for more than the tables can promise makes
    # this fail once in a while for no reason, which teaches everyone to
    # re-run the suite instead of reading it.
    assert len(set(said)) >= 6, said


@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 missing")
def test_alerts_only_is_still_silent_when_nothing_is_wrong():
    mod, b = _brain_with(
        {"sessions": [{"name": "x", "state": "working"}], "attention": None, "total": 1},
        {"efficiency": {"cacheHitRate": 0.9}}, alerts_only=True)
    assert b.line() is None


@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 missing")
def test_every_category_exists_in_both_languages_with_equal_depth():
    """A category with five English lines and one Portuguese line repeats five
    times as often for a Portuguese reader."""
    spec = importlib.util.spec_from_file_location("companion_lines", COMPANION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    en, pt = mod.LINES["en"], mod.LINES["pt"]
    assert set(en) == set(pt), set(en) ^ set(pt)
    for key in en:
        assert len(en[key]) == len(pt[key]), f"{key}: {len(en[key])} vs {len(pt[key])}"
        assert len(en[key]) >= 3, f"{key} has too few lines to rotate"


# ── it has to be findable ──

@needs_display
def test_it_roams_every_screen(monkeypatch):
    """Confined to the primary screen it never appears on the other monitor at
    all, which is most of the time someone spends looking somewhere."""
    mod, app, c = _companion(monkeypatch)
    if len(c.screens) < 2:
        pytest.skip("single monitor")
    hit = {(g.left(), g.top()) for g in
           (c._screen_at(*c._pick_target()) for _ in range(400))}
    assert len(hit) == len(c.screens), f"only reaches {len(hit)} of {len(c.screens)} screens"


@needs_display
def test_targets_land_on_a_real_screen(monkeypatch):
    """The union of two monitors has regions belonging to no display; standing
    in one is invisible while looking perfectly fine to the code."""
    mod, app, c = _companion(monkeypatch)
    for _ in range(300):
        x, y = c._pick_target()
        g = c._screen_at(x, y)
        assert g.left() <= x <= g.right() and g.top() <= y <= g.bottom(), (x, y)


@needs_display
def test_it_asks_to_be_on_every_virtual_desktop(monkeypatch):
    """Without this it lives on whichever desktop it was launched from and has
    to be hunted for."""
    mod, app, c = _companion(monkeypatch)
    called = []
    monkeypatch.setattr(mod.subprocess, "Popen", lambda cmd, **kw: called.append(cmd))
    c._make_sticky()
    assert called, "never asked"
    joined = " ".join(called[0])
    assert "_NET_WM_DESKTOP" in joined and "0xFFFFFFFF" in joined, joined
