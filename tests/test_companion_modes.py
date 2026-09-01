"""The companion's modes: signals, focus, escort, insistence and the channel.

Everything here is about a way the companion can go wrong that is invisible
from the outside. A mascot that renders `{name}` in its bubble, that re-enters
yesterday's focus session on a restart, that draws its bubble off the edge of
the screen, or that seizes the pointer without being asked, all look exactly
like a working one until the moment they do not.
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
COMPANION = REPO / "scripts" / "usage-buddy-companion.py"

needs_qt = pytest.mark.skipif(importlib.util.find_spec("PySide6") is None,
                              reason="PySide6 missing")
needs_display = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None or not os.environ.get("DISPLAY"),
    reason="PySide6 or X display missing")


def _load(name="companion_modes"):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    spec = importlib.util.spec_from_file_location(name, COMPANION)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _scenarios():
    """The signal scenarios, borrowed from the suite that owns them.

    Deliberately imported rather than copied. These tests check that what
    buddy_signals emits survives the trip through the Brain and reaches the
    bubble as a finished sentence; a second copy of the payloads here would
    drift from the first, and then this would be checking the trip taken by
    data nothing produces any more.
    """
    spec = importlib.util.spec_from_file_location(
        "signals_scenarios", REPO / "tests" / "test_buddy_signals.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["signals_scenarios"] = mod
    spec.loader.exec_module(mod)
    return mod.SCENARIOS


def _companion(mod=None):
    """A Companion with its polling neutralised, so tests drive it."""
    mod = mod or _load()
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    c = mod.Companion()
    c.poll_timer.stop()
    c._poll = lambda: None
    return mod, c


# ── every key the detector emits has to arrive as a finished sentence ──────

@needs_qt
@pytest.mark.parametrize("key", sorted(_scenarios()))
def test_every_signal_renders_without_a_leftover_placeholder(key, monkeypatch):
    """A placeholder nothing fills prints its own braces in the bubble.

    Checked through Brain.line() rather than against the signal's vars, so it
    covers the half the signal cannot see: the Brain re-derives `name` and
    `idle` when it rotates the subject, and its _pick() takes `now` as a
    keyword — a category that ever used {now} would have it swallowed by the
    signature and printed on screen.
    """
    mod = _load()
    scenarios = _scenarios()
    payload, usage, when = scenarios[key][0]
    signal = {s.key: s for s in mod.signals.detect(payload, usage, when)}[key]

    for lang in ("en", "pt"):
        brain = mod.Brain(lang)
        brain.sessions, brain.usage = payload, usage
        # Only the selection is forced; the signal itself came out of the real
        # detector on the real payload above. Without this the Brain would
        # answer with whatever outranks this key on the same desktop, and
        # twenty of the thirty categories would never be rendered at all.
        monkeypatch.setattr(mod.signals, "detect", lambda *a, **k: [signal])
        # Every line in the category, not one draw: the anti-repeat window
        # hands out a different sentence each time, and only one of them may
        # be the one carrying the unfilled placeholder.
        seen = set()
        for _ in range(len(mod.LINES[lang][key]) * 3):
            text = brain.line()
            assert text, f"{lang}/{key} rendered nothing"
            seen.add(text)
            assert not re.search(r"{\w+}", text), f"{lang}/{key}: {text}"
        assert len(seen) >= min(3, len(mod.LINES[lang][key]))


@needs_qt
def test_no_category_uses_a_placeholder_the_pick_signature_would_eat():
    """Brain._pick takes `now` as a keyword and passes the rest through as
    template variables. A line written with {now} in it would bind to the
    parameter instead of the template and print its own braces."""
    mod = _load()
    reserved = {"now", "key", "self"}
    for lang, table in mod.LINES.items():
        for key, lines in table.items():
            for line in lines:
                clash = set(re.findall(r"{(\w+)}", line)) & reserved
                assert not clash, f"{lang}/{key} uses reserved {sorted(clash)}"


# ── what survived the change of engine ─────────────────────────────────────

@needs_qt
def test_the_rotation_between_sessions_survived_the_signal_engine():
    """buddy_signals.detect is stateless and fills its vars from the first
    qualifying row. Reading its answer straight into the bubble names the same
    repository every poll — three sessions waiting become an hour of complaint
    about whichever one sorts first."""
    mod = _load()
    brain = mod.Brain("en")
    brain.sessions = {"total": 3, "attention": None, "sessions": [
        {"pid": n, "name": name, "state": "waiting", "idleSeconds": 300}
        for n, name in enumerate(("alpha", "beta", "gamma"), start=1)]}
    said = [brain.line() for _ in range(18)]
    named = {n for n in ("alpha", "beta", "gamma")
             if any(n in line for line in said)}
    assert named == {"alpha", "beta", "gamma"}, named


@needs_qt
def test_alerts_only_is_decided_by_priority_not_by_a_list_of_keys():
    """The mode used to mute everything below the session states by listing
    them. A quota window at 97% is an alert by every reading except that list,
    and it was silent — the whole band was written and unreachable."""
    mod = _load()
    brain = mod.Brain("en", alerts_only=True)
    brain.sessions = {"total": 0, "sessions": [], "attention": None}
    brain.usage = {"rateLimits": {"session": {"percentUsed": 97}}}
    line = brain.line()
    assert line, "a critical quota was muted by alerts-only"
    assert "97" in line, line


@needs_qt
def test_alerts_only_stays_quiet_on_a_healthy_desktop():
    """Silence is the point of the mode worth leaving on. Diagnosis is still
    true in ten minutes and is not an alert."""
    mod = _load()
    brain = mod.Brain("en", alerts_only=True)
    brain.sessions = {"total": 1, "attention": None,
                      "sessions": [{"pid": 1, "name": "x", "state": "working"}]}
    brain.usage = {"compaction": {"count": 99},
                   "efficiency": {"cacheHitRate": 0.1, "readPerOutput": 900}}
    assert brain.line() is None


@needs_qt
def test_alerts_only_still_reports_a_waiting_session():
    """The one thing the mode exists to say."""
    mod = _load()
    brain = mod.Brain("en", alerts_only=True)
    brain.sessions = {"total": 1, "attention": None, "sessions": [
        {"pid": 1, "name": "hub", "state": "waiting", "idleSeconds": 120}]}
    assert "hub" in (brain.line() or "")


# ── the focus block ────────────────────────────────────────────────────────

@needs_qt
def test_a_focus_block_silences_a_joke_and_lets_a_question_through():
    """A focus mode that still tells jokes is not a focus mode, it is a
    smaller font — and one that also swallows a session sitting on a question
    is a mute button, which is a different feature. Both halves at once."""
    mod = _load()
    brain = mod.Brain("en")
    brain.sessions = {"total": 1, "attention": None,
                      "sessions": [{"pid": 1, "name": "x", "state": "working"}]}
    assert brain.line(now=1000.0), "said nothing with no block running"

    brain.focus.start(1000.0, minutes=25)
    assert brain.line(now=1001.0) is None, "told a joke during a focus block"

    brain.sessions = {"total": 1, "attention": None, "sessions": [
        {"pid": 1, "name": "hub", "state": "asking"}]}
    assert "hub" in (brain.line(now=1001.0) or ""), "swallowed a blocked session"


def _fake_bus(mod, monkeypatch, iface, closed):
    """An inhibitor whose D-Bus connection is a record of what happened to it."""
    inhibitor = mod.NotificationInhibitor()
    monkeypatch.setattr(type(inhibitor), "_connect",
                        lambda self: ("connection", iface))
    monkeypatch.setattr(type(inhibitor), "_close",
                        staticmethod(lambda name: closed.append(name)))
    return inhibitor


@needs_qt
def test_a_cancelled_block_releases_the_notification_inhibition(monkeypatch):
    """The hold lives on a D-Bus connection of its own and is given back by
    closing it. A block that ends with the process needs nothing — the
    connection goes down with it — but a block called off leaves the process
    running, and without this the hold outlives the block it belonged to and
    stays until the mascot is closed.

    Not released with UnInhibit: the server exports UnInhibit(u), PySide6
    marshals a Python int as `i`, and the call is refused with "No such method
    'UnInhibit' ... (signature 'i')" while the hold stays up. Measured on this
    desktop.
    """
    mod = _load()
    calls, closed = [], []

    class FakeIface:
        def call(self, method, *args):
            calls.append((method, args))
            return 4242

    inhibitor = _fake_bus(mod, monkeypatch, FakeIface(), closed)
    assert inhibitor.hold("Focus block") == 4242
    assert inhibitor.cookie == 4242
    assert calls == [("Inhibit", (inhibitor.APP_ID, "Focus block", {}))], calls
    assert closed == [], "closed the connection while still holding it"

    assert inhibitor.release() is True
    assert inhibitor.cookie is None
    assert closed == ["connection"], closed
    # And releasing twice does not close a connection that is already gone.
    assert inhibitor.release() is False
    assert closed == ["connection"]


@needs_qt
def test_a_refused_hold_does_not_leave_a_connection_open(monkeypatch):
    """One connection per hold. A server that answers Inhibit with an error
    would otherwise leak a session-bus connection per focus block, in a process
    meant to run for days."""
    mod = _load()
    closed = []

    class AnswersAnError:
        def call(self, *_args):
            return type("Msg", (), {"arguments": staticmethod(list)})()

    inhibitor = _fake_bus(mod, monkeypatch, AnswersAnError(), closed)
    assert inhibitor.hold("Focus block") is None
    assert inhibitor.cookie is None
    assert closed == ["connection"], closed


@needs_qt
def test_two_holds_never_share_one_connection():
    """Qt keys D-Bus connections by name and hands back the existing one for a
    name already in use. Two inhibitors on one connection means releasing
    either takes the other's hold down with it."""
    mod = _load()
    first, second = mod.NotificationInhibitor(), mod.NotificationInhibitor()
    first._connection = f"{first.CONNECTION}-{id(first)}"
    second._connection = f"{second.CONNECTION}-{id(second)}"
    assert first._connection != second._connection


@needs_display
def test_a_finished_block_says_so_once_and_then_stops():
    """`done` is a state a clock stays in, not an event it passes through. An
    announcement bound to it repeats once per poll, forever, until someone
    starts another block to make it stop."""
    mod, c = _companion()
    said = []
    c._say = lambda text: said.append(text)
    c.start_focus(minutes=25)
    c.focus.start(0.0, minutes=25)          # a block that began long ago
    c._focus_phase = mod.focus_engine.PHASE_RUNNING

    c._focus_tick(60.0 * 25 + 1.0)
    c._focus_tick(60.0 * 25 + 21.0)
    c._focus_tick(60.0 * 25 + 41.0)
    overs = [text for text in said if text == c._t("focusOver")]
    assert len(overs) == 1, f"announced the end {len(overs)} times"
    assert c.focus.active is False


@needs_display
def test_the_last_minute_of_a_block_gives_it_frames_to_walk_back_in():
    """Parked in a corner it dozes at 200ms a frame. A block that flips
    straight from running to done leaves it no frames to move, so the end
    reads as a bubble appearing out of nowhere next to a motionless sprite."""
    mod, c = _companion()
    c.focus.start(0.0, minutes=25)
    c._focus_phase = mod.focus_engine.PHASE_RUNNING
    c.docked = True
    c._doze()
    assert c.frame_timer.interval() == mod.FRAME_MS_IDLE

    c._focus_tick(60.0 * 25 - mod.focus_engine.ENDING_SECONDS / 2)
    assert c._focus_phase == mod.focus_engine.PHASE_ENDING
    assert c.frame_timer.interval() == mod.FRAME_MS_ACTIVE, "no frames to return in"
    assert c.docked is False


@needs_qt
def test_the_inhibition_never_takes_the_companion_down(monkeypatch):
    """No session bus, no notification server, or a server that throws. Each
    costs the inhibition and nothing else: an exception on this path happens
    inside a focus block starting, and would take the block down with it."""
    mod = _load()

    class Refuses:
        def call(self, *_args):
            raise RuntimeError("no such interface")

    inhibitor = _fake_bus(mod, monkeypatch, Refuses(), [])
    assert inhibitor.hold("Focus block") is None
    assert inhibitor.release() is False

    unreachable = mod.NotificationInhibitor()
    monkeypatch.setattr(type(unreachable), "_connect", lambda self: None)
    assert unreachable.hold("Focus block") is None
    assert unreachable.release() is False


# ── the insistence ladder ──────────────────────────────────────────────────

@needs_qt
@pytest.mark.parametrize("step", ["off", "speak", "walk", "wave"])
def test_only_the_pointer_step_can_reach_the_rung_that_takes_the_mouse(step):
    """Rung 4 moves the user's cursor. It cannot be reached by waiting, by a
    long-running session or by a setting someone raised because the ladder
    looked incomplete — only by naming it."""
    mod = _load()
    options = mod.parse_args(["--insistence", step])
    assert options.insistence == step
    assert mod.INSISTENCE_CEILING[options.insistence] < 4

    # Both halves of the opt-in, because either alone would be enough to hide
    # a break in the other: the engine will not report a 4 without it...
    engine = mod.focus_engine.Insistence(allow_pointer=step == "pointer")
    rows = [{"pid": 7, "state": "asking", "idleSeconds": 0}]
    engine.update(rows, 0.0)
    levels = engine.update(rows, mod.focus_engine.POINTER_AFTER + 60.0)
    assert levels[7] <= 3, f"{step} reached rung {levels[7]}"
    # ...and the companion will not act on one above the ceiling either.
    assert min(4, mod.INSISTENCE_CEILING[step]) < 4


@needs_qt
def test_the_pointer_step_reaches_the_rung_it_is_named_for():
    """The negative above is only worth anything if the positive works: a
    ceiling that is always below four would pass every one of them."""
    mod = _load()
    assert mod.parse_args(["--insistence", "pointer"]).insistence == "pointer"
    assert mod.INSISTENCE_CEILING["pointer"] == 4
    engine = mod.focus_engine.Insistence(allow_pointer=True)
    rows = [{"pid": 7, "state": "asking", "idleSeconds": 0}]
    engine.update(rows, 0.0)
    assert engine.update(rows, mod.focus_engine.POINTER_AFTER + 60.0)[7] == 4


@needs_display
def test_the_last_rung_reuses_the_machine_that_already_moves_the_pointer():
    """A second way of moving someone's cursor is a second way of getting it
    wrong. The route, the speed profile and the deltas-not-positions rule were
    all bought with measurement once already."""
    mod, c = _companion()
    c.options = c.options._replace(insistence="pointer")
    c.insistence = mod.focus_engine.Insistence(allow_pointer=True)
    c.pointer = object()          # a pointer that exists, without opening one
    c.brain.sessions = {"total": 1, "attention": None, "sessions": [
        {"pid": 7, "name": "hub", "state": "asking", "idleSeconds": 0}]}
    c._insist(0.0)
    c._insist(mod.focus_engine.POINTER_AFTER + 60.0)
    assert c.tug_route is not None, "rung 4 did not start a carry"
    assert len(c.tug_route) == 3, "not the Bezier the existing machine drives"
    assert c.tug_until > 0.0


@needs_display
def test_insistence_holds_off_during_a_focus_block():
    """The ladder exists to interrupt, and a block is a decision not to be."""
    mod, c = _companion()
    c.options = c.options._replace(insistence="pointer")
    c.insistence = mod.focus_engine.Insistence(allow_pointer=True)
    c.pointer = object()
    c.brain.sessions = {"total": 1, "attention": None, "sessions": [
        {"pid": 7, "name": "hub", "state": "asking", "idleSeconds": 0}]}
    c.focus.start(0.0, minutes=60)
    c._insist(0.0)
    c._insist(mod.focus_engine.POINTER_AFTER + 60.0)
    assert c.tug_route is None, "took the pointer during a focus block"


# ── the command channel ────────────────────────────────────────────────────

def _issued(mod, companion, seconds):
    """An ISO stamp `seconds` away from the moment the process came up."""
    from datetime import timedelta
    return (companion.started_at + timedelta(seconds=seconds)).isoformat().replace(
        "+00:00", "Z")


@needs_display
def test_a_command_issued_before_the_process_started_is_ignored():
    """The file is state, not an event: it holds the last command written
    until the next one replaces it. Restarted the next morning, a companion
    that does not compare issuedAt re-enters the focus block someone asked for
    yesterday — which is the reason the timestamp is in the format."""
    mod, c = _companion()
    assert c.apply_command({"command": "focus.start", "minutes": 25,
                            "issuedAt": _issued(mod, c, -86400)}) is False
    assert c.focus.active is False


@needs_display
def test_a_command_issued_after_the_process_started_is_executed():
    """The other half. A comparison that rejected everything would pass the
    test above and leave the button on the widget doing nothing."""
    mod, c = _companion()
    assert c.apply_command({"command": "focus.start", "minutes": 5,
                            "issuedAt": _issued(mod, c, 5)}) is True
    assert c.focus.active is True
    assert 0 < c.focus.remaining(__import__("time").monotonic()) <= 5 * 60


@needs_display
def test_the_same_command_is_not_executed_twice():
    """A rename fires the watcher on both the file and the directory holding
    it, so one write arrives as two notifications. Re-running focus.start
    restarts the block from zero every time the watcher stutters."""
    mod, c = _companion()
    payload = {"command": "focus.start", "minutes": 25,
               "issuedAt": _issued(mod, c, 5)}
    assert c.apply_command(payload) is True
    assert c.apply_command(payload) is False


@needs_display
def test_a_command_without_a_timestamp_is_dropped():
    """There is nothing to compare it against, which makes it exactly as
    trustworthy as the one left in the file yesterday."""
    _mod, c = _companion()
    assert c.apply_command({"command": "focus.start", "minutes": 25}) is False
    assert c.apply_command({"command": "focus.start", "minutes": 25,
                            "issuedAt": "sometime"}) is False
    assert c.focus.active is False


@needs_display
def test_focus_stop_arrives_over_the_channel():
    mod, c = _companion()
    c.apply_command({"command": "focus.start", "minutes": 25,
                     "issuedAt": _issued(mod, c, 5)})
    assert c.focus.active is True
    assert c.apply_command({"command": "focus.stop",
                            "issuedAt": _issued(mod, c, 6)}) is True
    assert c.focus.active is False


@needs_qt
def test_a_half_written_command_file_is_ignored_rather_than_raised(tmp_path):
    """The widget writes to a temporary file and renames it over the target,
    but a directory watcher fires on the temporary file appearing too, and
    that one is read mid-write. This runs inside a Qt slot: an exception does
    not lose a command, it loses the channel."""
    mod = _load()
    path = tmp_path / "companion-command.json"
    for content in ('{"command": "focus.st', "", "null", "[]", "not json at all"):
        path.write_text(content, encoding="utf-8")
        assert mod.read_command(path) is None, content
    assert mod.read_command(tmp_path / "absent.json") is None
    path.write_text(json.dumps({"command": "focus.stop", "issuedAt": "x"}),
                    encoding="utf-8")
    assert mod.read_command(path) == {"command": "focus.stop", "issuedAt": "x"}


@needs_display
def test_the_watcher_is_re_added_after_every_command(tmp_path, monkeypatch):
    """QFileSystemWatcher drops a path whose file was removed, and a rename
    over the target removes the inode it was holding. Without re-adding,
    exactly one command is ever delivered and the channel is dead after it."""
    mod, c = _companion()
    target = tmp_path / "companion-command.json"
    monkeypatch.setattr(mod, "COMMAND_FILE", target)
    target.write_text("{}", encoding="utf-8")
    c._rewatch_command()
    assert str(target) in c.watcher.files()

    # What a rename over the target does to the watch.
    c.watcher.removePath(str(target))
    assert str(target) not in c.watcher.files()
    c._command_changed()
    assert str(target) in c.watcher.files(), "the channel died after one command"


# ── the bubble has to be on the screen ─────────────────────────────────────

@needs_display
@pytest.mark.parametrize("edge", ["left", "right"])
def test_the_bubble_fits_on_screen_with_the_companion_docked(edge):
    """It always opened to the right and the window always grew to the right,
    while max_x reserves only the character's own width — so parked against
    the right-hand edge the bubble was laid out past the end of the screen.
    The dodge in _poll that steps away from the edges first does not cover it:
    that one only runs when it is not docked, and docked in a corner is
    exactly the case."""
    mod, c = _companion()
    c.docked = True
    c.pos_x = float(c.min_x if edge == "left" else c.max_x)
    c.pos_y = float(c.max_y)
    c.bubble = "A sentence long enough to need most of the bubble's width."
    c._resize_for_bubble()

    slack = mod.sprites.SCALE          # _place snaps to the sprite grid
    assert c.x() >= c.bounds.left() - slack, (
        f"{edge}: window starts at {c.x()}, screen at {c.bounds.left()}")
    assert c.x() + c.width() <= c.bounds.right() + 1 + slack, (
        f"{edge}: window ends at {c.x() + c.width()}, screen at {c.bounds.right()}")


@needs_display
def test_the_character_does_not_move_when_the_bubble_opens_to_its_left():
    """The window grows leftwards to make room, so the sprite has to be drawn
    that far into it. Drawn at zero it slides a bubble's width across the
    screen every time it speaks."""
    mod, c = _companion()
    c.docked = True
    c.pos_x, c.pos_y = float(c.max_x), float(c.max_y)
    c.bubble = "A sentence long enough to need most of the bubble's width."
    c._resize_for_bubble()
    assert c.bubble_pad > 0, "did not open to the left with no room on the right"
    assert abs((c.x() + c.bubble_pad) - c.pos_x) <= mod.sprites.SCALE


@needs_display
def test_the_bubble_opens_to_the_right_when_there_is_room():
    """The common case, and the one that leaves the window where it was."""
    mod, c = _companion()
    c.pos_x, c.pos_y = float(c.min_x), float(c.max_y)
    c.bubble = "Short."
    c._resize_for_bubble()
    assert c.bubble_pad == 0
    assert abs(c.x() - c.pos_x) <= mod.sprites.SCALE


def _painted_span(image, first_row, last_row):
    """The first and last x painted on any row in the band, or None."""
    xs = [x
          for row in range(first_row, min(last_row, image.height()))
          for x in range(image.width())
          if image.pixelColor(x, row).alpha() > 0]
    return (min(xs), max(xs)) if xs else None


@needs_display
def test_the_sprite_is_drawn_into_the_window_the_bubble_pushed_left():
    """Moving the window left is only half of it. The sprite is drawn at a
    fixed x inside that window, so left at zero it is painted where the
    window's new left edge is — which is a bubble's width away from where the
    character was standing. On screen it teleports sideways every time it
    speaks and back again when the bubble closes.

    Read off the painted pixels rather than off the offset variable: an offset
    that is computed and then not used looks identical from the outside.
    """
    mod, c = _companion()
    c.options = c.options._replace(shadow=False)   # the shadow moves too
    c.docked = True
    c.pos_x, c.pos_y = float(c.max_x), float(c.max_y)
    c.bubble = "A sentence long enough to need most of the bubble's width."
    c._resize_for_bubble()
    assert c.bubble_pad > 0, "did not open to the left with no room on the right"

    # Below the bubble's own box, so what is left in the band is the sprite.
    below_bubble = 2 + c.bubble_size[1] + 2
    span = _painted_span(c.grab().toImage(), below_bubble, c.height())
    assert span, "nothing was painted on the sprite's own rows"
    assert span[0] >= c.bubble_pad - mod.sprites.SCALE, (
        f"sprite painted from x={span[0]}, window pushed left by {c.bubble_pad}")


@needs_display
def test_the_shadow_is_painted_and_no_shadow_takes_it_away():
    """A setting that parses and changes nothing is an option on the user's
    screen that does nothing when they change it, with no warning anywhere."""
    _mod, c = _companion()
    c.bubble = ""
    c.dragging = False
    c.options = c.options._replace(shadow=True)
    with_shadow = c.grab().toImage()
    c.options = c.options._replace(shadow=False)
    without = c.grab().toImage()
    assert with_shadow != without, "--no-shadow changed nothing on screen"


@needs_display
def test_the_shadow_drawn_is_the_one_in_the_sheet():
    """buddy_sprites ships the contact shadow as its own image, on the body's
    own grid and with an alpha palette, precisely so it is not an antialiased
    ellipse laid next to pixel art. Drawing anything else here is a second
    shadow that does not match the sprite it belongs to.

    Also the case where it is not there: a sheet built before the art landed
    has to paint no shadow rather than raise on a missing key.
    """
    _mod, c = _companion()
    c.bubble = ""
    c.dragging = False
    c.options = c.options._replace(shadow=True)
    assert c.sheet.get("shadow") is not None, "the sheet has no shadow to draw"
    drawn = c.grab().toImage()

    without_art = dict(c.sheet)
    without_art.pop("shadow")
    c.sheet = without_art
    assert c.grab().toImage() != drawn, "the shadow does not come from the sheet"

    c.options = c.options._replace(shadow=False)
    assert c.grab().toImage() == c.grab().toImage()   # and it does not raise


@needs_display
def test_a_character_in_the_air_casts_no_shadow(monkeypatch):
    """A shadow that stays under a sprite being carried across the screen is a
    second object glued to its feet. It is a separate image so that this can
    be decided here, at paint time.

    The pose is held still across the two grabs: being dragged also swaps the
    sprite for a swinging one, so comparing whole frames would pass on that
    difference alone and watch nothing.
    """
    mod, c = _companion()
    c.bubble = ""
    c.options = c.options._replace(shadow=True)
    monkeypatch.setattr(type(c), "swing_frame", lambda self: self.frame)

    shadow = c.sheet["shadow"]
    band = (c.height() - shadow.height(), c.height())

    c.dragging = False
    grounded = _painted_span(c.grab().toImage(), *band)
    c.dragging = True
    airborne = _painted_span(c.grab().toImage(), *band)
    assert grounded != airborne, "kept its shadow while held"
    assert grounded is not None, "cast no shadow while standing either"


@needs_display
def test_the_focus_block_draws_how_much_of_it_is_left():
    """`fraction` exists to be drawn. A block with no readout is a mascot that
    has gone quiet for no visible reason, which is the same thing as broken."""
    _mod, c = _companion()
    c.bubble = ""
    idle = c.grab().toImage()
    c.focus.start(__import__("time").monotonic(), minutes=25)
    running = c.grab().toImage()
    assert idle != running, "a focus block looks exactly like no focus block"


# ── art that has not landed yet ────────────────────────────────────────────

@needs_qt
def test_a_clip_the_sheet_has_not_got_falls_back_instead_of_raising():
    """buddy_sprites.Animator looks its clip up in CLIPS on every frame, so a
    name that is not there raises inside the frame timer — which is not a
    dropped frame, it is the companion gone. The poses for focus and
    insistence are drawn separately from this code and may land later."""
    mod = _load()
    assert mod.clip_or_fallback("no-such-clip-anywhere") in mod.sprites.CLIPS
    for name in mod.CLIP_FALLBACK:
        assert mod.clip_or_fallback(name) in mod.sprites.CLIPS


@needs_display
def test_the_animation_survives_a_sheet_without_the_focus_pose(monkeypatch):
    """The whole point of the fallback: with `sit` missing, a focus block must
    still animate rather than take the process down on the next tick."""
    mod, c = _companion()
    thinned = {name: clip for name, clip in mod.sprites.CLIPS.items()
               if name not in ("sit", "wave", "point")}
    monkeypatch.setattr(mod.sprites, "CLIPS", thinned)
    c.focus.start(0.0, minutes=25)
    c._animate(0.02, 1.0, moving=False)
    assert c.anim.base in thinned, c.anim.base
    assert c.frame, "no frame came back"


# ── the escort ─────────────────────────────────────────────────────────────

@needs_qt
def test_an_escort_talks_about_nothing_but_the_session_it_is_holding():
    """Rotation is right for surveillance and wrong for concentration: a
    person who has decided to deal with one session does not want to hear
    about the other two on the next poll."""
    mod = _load()
    brain = mod.Brain("en")
    brain.sessions = {"total": 3, "attention": None, "sessions": [
        {"pid": n, "name": name, "state": "waiting", "idleSeconds": 300}
        for n, name in enumerate(("alpha", "beta", "gamma"), start=1)]}
    brain.escort.lock(2)
    said = [brain.line() for _ in range(12)]
    assert all("beta" in line for line in said), said


@needs_qt
def test_an_escort_on_a_session_that_is_gone_lets_go():
    """A lock on a pid that never comes back filters every list down to
    nothing, and the companion goes mute for good with no way to tell why."""
    mod = _load()
    brain = mod.Brain("en")
    brain.sessions = {"total": 1, "attention": None, "sessions": [
        {"pid": 1, "name": "alpha", "state": "waiting", "idleSeconds": 300}]}
    brain.escort.lock(999)
    assert "alpha" in (brain.line() or "")
    assert brain.escort.locked_on is None


# ── the quiet hours ────────────────────────────────────────────────────────

# The history the machine this was written on actually has: eighteen hours
# touched, peak in the afternoon, almost nothing before 09:00.
PEAK_HOURS = {"9": 19, "10": 43, "11": 63, "12": 41, "13": 28, "14": 76,
              "15": 50, "16": 60, "17": 45, "18": 47, "19": 33, "20": 8}


def _at_hour(hour):
    """A Unix timestamp landing on `hour` in local time."""
    import time as _time
    base = _time.time()
    local = _time.localtime(base)
    return base + (hour - local.tm_hour) * 3600


@needs_qt
def test_the_quiet_hours_hold_back_a_diagnosis_and_not_a_question():
    """Outside the hours this person works, a cache-hit lecture can wait for
    the morning. A session blocked on a question cannot: it stays blocked
    until a human arrives, whatever the clock says."""
    mod = _load()
    usage = {"lifetime": {"peakHours": PEAK_HOURS},
             "efficiency": {"cacheHitRate": 0.1}}
    brain = mod.Brain("en", quiet_hours=True)
    brain.usage = usage
    brain.sessions = {"total": 0, "sessions": [], "attention": None}
    assert brain.line(wall=_at_hour(4)) is None, "lectured at four in the morning"
    assert brain.line(wall=_at_hour(14)) is not None, "silent in the working day"

    brain.sessions = {"total": 1, "attention": None, "sessions": [
        {"pid": 1, "name": "hub", "state": "asking"}]}
    assert "hub" in (brain.line(wall=_at_hour(4)) or ""), "swallowed a question"


@needs_display
@pytest.mark.parametrize("level", ["off", "light", "full"])
def test_the_meme_setting_decides_how_often_a_line_comes_with_a_prop(level):
    """Three values that have to be three behaviours, and the widget's own
    labels say which: "plain sprite, no props", "a prop now and then", "a prop
    on most lines". A setting whose values all do the same thing is a control
    the user moves with nothing happening and no warning that it is inert.

    Off is the half that matters most and is exact rather than statistical: a
    single prop under a setting that promised none is the bug being watched
    for, and a threshold would let it through.
    """
    mod = _load()
    _m, c = _companion(mod)
    c.options = c.options._replace(memes=level)
    rolls = [c._roll_prop() for _ in range(400)]
    share = sum(rolls) / len(rolls)
    if level == "off":
        assert not any(rolls), "carried a prop with props switched off"
        return
    assert 0.0 < share < 1.0, share
    # And the order of the three is the order of the labels.
    lighter = mod.MEME_PROP_CHANCE["light"]
    assert 0.0 < lighter < mod.MEME_PROP_CHANCE["full"], mod.MEME_PROP_CHANCE


@needs_display
def test_a_line_with_a_prop_is_animated_holding_it():
    """The setting is only worth anything if the decision reaches the sprite.
    A flag that is rolled and then not read is the same as no flag."""
    mod = _load()
    _m, c = _companion(mod)
    c.bubble = "Something to say."
    c.dragging = False
    c.alert_until = c.insist_until = c.tug_until = 0.0

    c.prop_line = False
    c._animate(0.02, 1.0, moving=False)
    plain = c.anim.base
    c.prop_line = True
    c._animate(0.02, 1.0, moving=False)
    assert c.anim.base != plain, "the prop never reaches the animation"
    assert c.anim.base in mod.sprites.CLIPS


@needs_display
def test_the_prop_is_decided_once_per_line_and_not_once_per_frame():
    """Rolled on the frame timer, the book appears and vanishes thirty times a
    second, which is not a prop, it is a flicker."""
    mod = _load()
    _m, c = _companion(mod)
    c.options = c.options._replace(memes="full")
    c._say("One line.")
    decided = c.prop_line
    for _ in range(30):
        c._animate(0.02, 1.0, moving=False)
    assert c.prop_line is decided, "the decision changed under the frame timer"


@needs_qt
def test_with_the_setting_off_the_hour_of_day_silences_nothing():
    """The setting has an off, and off has to mean off. A companion that goes
    quiet at night after being told not to reads as broken, not as tactful."""
    mod = _load()
    brain = mod.Brain("en")
    brain.usage = {"lifetime": {"peakHours": PEAK_HOURS},
                   "efficiency": {"cacheHitRate": 0.1}}
    brain.sessions = {"total": 0, "sessions": [], "attention": None}
    assert brain.line(wall=_at_hour(4)) is not None


# ── the command line the widget writes ─────────────────────────────────────

@needs_qt
@pytest.mark.parametrize("argv,field,expected", [
    (["--insistence", "pointr"], "insistence", "walk"),
    (["--insistence"], "insistence", "walk"),
    (["--insistence", "POINTER"], "insistence", "pointer"),
    (["--memes", "loud"], "memes", "light"),
    (["--memes", "full"], "memes", "full"),
    (["--focus-minutes", "abc"], "focus_minutes", 25),
    (["--focus-minutes", "0"], "focus_minutes", 1),
    (["--focus-minutes", "99999"], "focus_minutes", 240),
    (["--focus-minutes", "50"], "focus_minutes", 50),
])
def test_a_bad_value_from_the_config_is_clamped_and_never_fatal(argv, field, expected):
    """These values come out of a KDE config file — a text file a person can
    edit — by way of a shell command line. argparse answers a bad `choices` or
    a bad `type=int` with SystemExit(2), so a typo would mean no mascot at
    all, with the failure invisible from the widget, which never sees an exit
    code."""
    mod = _load()
    assert getattr(mod.parse_args(argv), field) == expected


@needs_qt
def test_an_unknown_flag_does_not_stop_the_companion_starting():
    """A newer widget talking to an older companion. That should cost the flag
    it does not understand, not the process."""
    mod = _load()
    options = mod.parse_args(["--pt", "--some-flag-from-the-future", "3", "--escort"])
    assert options.lang == "pt"
    assert options.escort is True


@needs_qt
def test_the_flags_that_were_already_there_still_mean_what_they_did():
    """The parse was `"--codex" in sys.argv` and had to change to take values.
    Everything the old one recognised has to survive the rewrite."""
    mod = _load()
    options = mod.parse_args(["--codex", "--pt", "--alerts-only", "--live",
                              "--self-test"])
    assert (options.brand, options.lang) == ("codex", "pt")
    assert options.alerts_only and options.live and options.self_test
    plain = mod.parse_args([])
    assert (plain.brand, plain.lang) == ("claude", "en")
    assert not plain.alerts_only and not plain.live and not plain.self_test


@needs_qt
@pytest.mark.parametrize("argv,field,expected", [
    (["--no-quiet-hours"], "quiet_hours", False),
    ([], "quiet_hours", True),
    (["--no-shadow"], "shadow", False),
    ([], "shadow", True),
    (["--escort"], "escort", True),
    ([], "escort", False),
])
def test_every_switch_the_widget_emits_reaches_the_options(argv, field, expected):
    """The widget's syncCompanion writes these six spellings and no others.
    One that parses to nothing is a setting on the user's screen that does
    nothing when they change it, with no warning anywhere."""
    mod = _load()
    assert getattr(mod.parse_args(argv), field) is expected


@needs_display
@pytest.mark.parametrize("lang", ["en", "pt"])
def test_every_menu_string_exists_in_both_languages(lang):
    """_t looks its key up and hands back the value with no default, so a key
    added in English and forgotten in Portuguese is a KeyError raised while a
    menu is being built — which is a right-click that kills the mascot."""
    mod = _load()
    used = sorted(set(re.findall(r'_t\("(\w+)"\)', COMPANION.read_text())))
    assert len(used) > 10, f"the scan found only {used}"
    _m, c = _companion(mod)
    c.lang = lang
    for key in used:
        assert c._t(key), f"{lang}/{key} is empty"


# ── the installation gate ──────────────────────────────────────────────────

@needs_display
def test_self_test_still_prints_its_json_and_exits_zero():
    """This is what the installer runs to decide the companion works. A change
    that breaks it does not break the mascot visibly — it stops the mascot
    being installed at all."""
    result = subprocess.run([sys.executable, str(COMPANION), "--self-test"],
                            capture_output=True, text=True, timeout=60,
                            env={**os.environ, "QT_QPA_PLATFORM": "xcb"})
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert set(report) == {"movedX", "movedY", "geometry", "frameMs"}, report
    assert report["movedX"] > 10 and report["movedY"] > 10, report


# ── the defaults the widget and the companion have to share ────────────────

# Which entry in main.xml decides which field of Options, and how its text
# becomes that field's value. The mapping is written here because it is the
# only part that is not in either file; the values are read from main.xml, so
# a default changed there and forgotten here fails rather than drifting. A
# second copy of the numbers in this file would agree with itself forever.
XML_TO_OPTION = {
    "buddyFocusMinutes": ("focus_minutes", int),
    "buddyInsistence": ("insistence", str),
    "buddyQuietHours": ("quiet_hours", lambda text: text == "true"),
    "buddyMemes": ("memes", str),
    "buddyShadow": ("shadow", lambda text: text == "true"),
    "buddyEscort": ("escort", lambda text: text == "true"),
    "buddyVoice": ("live", lambda text: text == "claude"),
}

# buddyMode decides whether the companion runs at all, which is
# companion-ctl.sh's business rather than a value on its command line.
UNMAPPED_BUDDY_ENTRIES = {"buddyMode"}


def _kcfg_defaults():
    """Every entry in main.xml, name to default text, namespace-insensitive."""
    import xml.etree.ElementTree as ET
    root = ET.parse(REPO / "plasmoid" / "contents" / "config" / "main.xml").getroot()
    out = {}
    for entry in root.iter():
        if not entry.tag.endswith("entry"):
            continue
        default = ""
        for child in entry:
            if child.tag.endswith("default"):
                default = (child.text or "").strip()
        out[entry.get("name")] = default
    return out


@needs_qt
@pytest.mark.parametrize("entry", sorted(XML_TO_OPTION))
def test_the_companions_defaults_are_the_widgets_defaults(entry):
    """The invariant was written in a comment above parse_args and never
    checked, and one of the seven had already drifted: buddyQuietHours
    defaulted to true in the widget and false in the parser, so the same
    desktop got a companion that talks at night when it was started by hand
    and one that does not when it was started by the applet.

    Read from main.xml rather than from a list here: a copy of the values in
    this file would go stale in exactly the silence this is watching for.
    """
    mod = _load()
    defaults = _kcfg_defaults()
    assert entry in defaults, f"{entry} is not declared in main.xml at all"
    field, convert = XML_TO_OPTION[entry]
    expected = convert(defaults[entry])
    actual = getattr(mod.parse_args([]), field)
    assert actual == expected, (
        f"{entry} is {defaults[entry]!r} in main.xml and {actual!r} in "
        f"parse_args([]).{field}")


def test_every_companion_setting_is_mapped_or_named_as_unmapped():
    """The parity test above only covers what is in its table, so a setting
    added to main.xml and never mapped would pass it by being absent."""
    buddy = {name for name in _kcfg_defaults() if name.startswith("buddy")}
    assert buddy == set(XML_TO_OPTION) | UNMAPPED_BUDDY_ENTRIES, (
        "a buddy setting is neither compared with the companion's default nor "
        f"declared as not being one: {sorted(buddy.symmetric_difference(set(XML_TO_OPTION) | UNMAPPED_BUDDY_ENTRIES))}")


# ── a file that is valid JSON and the wrong shape ──────────────────────────

# All of these are things sessions.json can contain: a collector caught
# mid-write, a hand-edited file, an older or newer writer. None of them is
# falsy, which is what `or {}` and `or []` catch and the whole reason they are
# not enough.
BROKEN_PAYLOADS = [
    {"sessions": 1},
    {"sessions": "ti"},
    {"sessions": {"one": 1}},
    {"sessions": [1, "ti", None]},
    {"sessions": [{"name": "ok", "state": "waiting", "idleSeconds": 5}, 7]},
    {"attention": "ti", "sessions": []},
    {"attention": {"name": "no pid"}, "sessions": []},
    {"attention": 7, "sessions": []},
    [],
    1,
    "broken",
]


@needs_display
@pytest.mark.parametrize("payload", BROKEN_PAYLOADS,
                         ids=lambda p: repr(p)[:32])
def test_a_payload_of_the_wrong_shape_does_not_end_the_poll(payload, monkeypatch):
    """Measured consequence, which is worse than a crash: PySide6 prints the
    traceback and the timer keeps firing, so the character goes on walking
    around while brain.line() raises every twenty seconds — it never speaks
    again, and _insist, which is called after it, never runs at all. The file
    is still on disk next tick, so it does not recover.
    """
    mod, c = _companion()
    insisted = []
    monkeypatch.setattr(type(c), "_insist", lambda self, now: insisted.append(now))
    monkeypatch.setattr(type(c), "_say", lambda self, text: None)
    monkeypatch.setattr(mod.subprocess, "Popen", lambda cmd, **kw: None)
    monkeypatch.setattr(mod, "FOCUS_HELPER", Path("/bin/true"))
    c.brain.refresh = lambda: None
    c.brain.sessions = payload
    c.brain.usage = {}

    assert c.brain.line() is None or isinstance(c.brain.line(), str)
    # The class's own poll: _companion replaces the instance's with a no-op,
    # and a test that called that one would pass on any companion at all.
    type(c)._poll(c)
    assert insisted, "the poll died before the insistence ladder"

    # The same payload through everything else that reads it: the two menus,
    # which are one right-click away, and the click that raises a terminal.
    from PySide6.QtWidgets import QMenu
    menu = QMenu()
    c._add_escort_menu(menu)
    c._add_repo_menu(menu)
    c._go_to_session()


@needs_display
def test_a_click_still_raises_a_terminal_when_the_payload_is_ordinary(monkeypatch):
    """The negative above passes on a companion whose click does nothing at
    all, so here is the positive: the pid still reaches the helper."""
    mod, c = _companion()
    called = []
    monkeypatch.setattr(mod.subprocess, "Popen", lambda cmd, **kw: called.append(cmd))
    monkeypatch.setattr(mod, "FOCUS_HELPER", Path("/bin/true"))
    c.brain.sessions = {"attention": {"pid": 4242, "name": "repo", "state": "asking"},
                        "sessions": [{"pid": 4242, "name": "repo", "state": "asking"}]}
    c._go_to_session()
    assert called and called[0][-1] == "4242", called


# ── the readings do not pile up ────────────────────────────────────────────

@needs_display
def test_a_finished_reading_is_destroyed_rather_than_kept(tmp_path, monkeypatch):
    """Every reading is a QProcess parented to the widget, and a parent keeps
    its children until it dies. With --live the refill runs on its own timer,
    up to fifteen an hour, on a process whose normal lifetime is a desktop
    session — so this is thousands of dead QProcess objects in a week.
    """
    import time
    from PySide6.QtCore import QEvent, QProcess
    from PySide6.QtWidgets import QApplication
    mod, c = _companion()
    monkeypatch.setattr(type(c), "_say", lambda self, text: None)
    # A command that exists, says nothing and exits at once. The point is the
    # object's lifetime, not what came back on stdout.
    monkeypatch.setattr(mod.repo_brief, "build_command",
                        lambda prompt, lang="en", model="haiku": ["/bin/echo", "{}"])
    app = QApplication.instance()
    for _ in range(10):
        c._ask_about({"cwd": str(tmp_path), "name": "hub"})
        deadline = time.monotonic() + 10.0
        while c.asking is not None and time.monotonic() < deadline:
            app.processEvents()
        assert c.asking is None, "the reading never finished"
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    alive = [child for child in c.children() if isinstance(child, QProcess)]
    assert not alive, f"{len(alive)} finished readings are still parented to it"
