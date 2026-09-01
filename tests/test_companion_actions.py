"""Throwing it, dropping a folder on it, perching, and the other mascot.

Two modules were written for the companion and nothing called them. Code that
nothing reaches is not half-finished, it is absent: it passes its own tests
forever while the behaviour it describes has never once happened on a desktop.
These are the tests of the seam rather than of the modules — buddy_actions and
buddy_peers have their own suites, and every assertion here is about the
companion reaching them and acting on the answer.

The four seams, and what each one costs when the wiring is wrong. A release
that reads as a throw when it was a placement takes the corner someone put the
character in away from them. A drop that is refused in silence is
indistinguishable from a drop the mascot never noticed. A window lookup on the
frame path blocks the character for a twentieth of a second, thirty times a
second. And a presence file left behind by a companion that has quit keeps it
visible to the other one for five seconds of walking toward nothing.
"""
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
COMPANION = REPO / "scripts" / "usage-buddy-companion.py"

sys.path.insert(0, str(REPO / "scripts"))
import buddy_actions as actions          # noqa: E402
import buddy_peers as peers              # noqa: E402

needs_qt = pytest.mark.skipif(importlib.util.find_spec("PySide6") is None,
                              reason="PySide6 missing")
needs_display = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None or not os.environ.get("DISPLAY"),
    reason="PySide6 or X display missing")

# Measured on this machine: the command line of a companion started by
# companion-ctl.sh. argv[0] is the interpreter, which is the trap that script
# documents having paid for.
COMPANION_ARGV = ["/usr/bin/python3",
                  "/home/ti/.local/bin/usage-buddy-companion.py", "--codex"]


def _load(name="companion_actions"):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    spec = importlib.util.spec_from_file_location(name, COMPANION)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _companion(mod=None, poll=False):
    """A Companion with both timers stopped, so the test owns the clock.

    `poll` keeps the real _poll, which the mood tests need: everything else
    replaces it, because a poll that runs on its own reads the live sessions
    file and starts talking over the test.
    """
    mod = mod or _load()
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    c = mod.Companion()
    c.poll_timer.stop()
    c.frame_timer.stop()
    if not poll:
        c._poll = lambda: None
    return mod, c


def _release(companion):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    companion.mouseReleaseEvent(
        QMouseEvent(QMouseEvent.MouseButtonRelease, QPointF(0, 0),
                    Qt.LeftButton, Qt.NoButton, Qt.NoModifier))


def _gesture(now, speed, samples=4, step=0.03):
    """A drag whose last 90 ms happened at exactly `speed` px/s, going right.

    Built rather than driven through real events on purpose: two mouse events
    a millisecond apart divided into three pixels is a launch, and a test that
    depends on how fast the machine running it happens to be proves nothing
    about the threshold it is meant to be checking.
    """
    return [(now - (samples - 1 - i) * step, 400.0 + i * step * speed, 300.0)
            for i in range(samples)]


def _fake_proc(root, pid, argv=None):
    """A /proc/<pid>/cmdline that says what we want it to say."""
    entry = Path(root) / str(pid)
    entry.mkdir(parents=True, exist_ok=True)
    (entry / "cmdline").write_bytes(
        b"\0".join(part.encode("utf-8") for part in (argv or COMPANION_ARGV)) + b"\0")


def _yard(tmp_path, mine, theirs, brand="claude", at=1000.0, x=0.0, y=0.0):
    """A presence directory with one other companion in it, and ours reading.

    The peer is written through PeerDirectory rather than by hand so the file
    is the one the real thing writes, down to the payload's own pid field.
    """
    root = tmp_path / "proc"
    _fake_proc(root, theirs)
    _fake_proc(root, mine)
    yard = tmp_path / "peers"
    yard.mkdir(parents=True, exist_ok=True)
    peers.PeerDirectory(yard, pid=theirs, proc=str(root)).publish(
        brand, x, y, at)
    return peers.PeerDirectory(yard, pid=mine, proc=str(root))


# ── the throw ──────────────────────────────────────────────────────────────

@needs_display
def test_a_slow_release_is_a_placement_and_still_snaps_to_the_corner(monkeypatch):
    """The behaviour that was there before the throw existed, unchanged.

    Putting the character in a corner is an instruction, and a release slower
    than the character walks is somebody putting it down. If that ever becomes
    a throw, the corner someone chose is taken away from them by a gesture
    they did not make.
    """
    mod, c = _companion()
    monkeypatch.setattr(type(c), "_say", lambda self, text: None)
    now = time.monotonic()
    c.pos_x, c.pos_y = float(c.min_x + 2), float(c.min_y + 2)
    c.recent_drags, c.drag_distance = [], 0.0
    c.drag_started = now
    c.dragging = True
    c.throw_samples = _gesture(now, actions.THROW_MIN_SPEED - 30)
    _release(c)
    assert c.flying is False, "a placement became a throw"
    assert c.docked is True, "the corner it was put in was not kept"
    assert (c.pos_x, c.pos_y) == (float(c.min_x), float(c.min_y))


@needs_display
def test_a_fast_release_leaves_the_hand_instead_of_snapping(monkeypatch):
    """And the other half: let go mid-gesture and it keeps the speed."""
    mod, c = _companion()
    monkeypatch.setattr(type(c), "_say", lambda self, text: None)
    snapped = []
    monkeypatch.setattr(type(c), "_snap", lambda self: snapped.append(True))
    now = time.monotonic()
    c.pos_x, c.pos_y = float(c.min_x + 2), float(c.min_y + 2)
    c.recent_drags, c.drag_distance = [], 0.0
    c.drag_started = now
    c.dragging = True
    c.throw_samples = _gesture(now, 900.0)
    _release(c)
    assert c.flying is True, "the throw was thrown away"
    assert not snapped, "a throw ended in a snap to the edge"
    assert c.docked is False
    assert c.vel_x > actions.THROW_MIN_SPEED, c.vel_x
    assert c.throw_samples == [], "the gesture was kept for the next release"


@needs_display
def test_the_gesture_reaches_the_release_through_the_move_events():
    """The samples have to be collected where the hand actually is.

    Bounded there too: buddy_actions walks back only as far as its own window,
    and a list that grows for as long as somebody keeps dragging is a leak on
    the one path a person can hold open indefinitely.
    """
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    mod, c = _companion()
    c.press_pos = QPointF(0.0, 0.0)
    c.drag_offset = QPointF(0.0, 0.0)
    c.hand = None
    c.dragging = False
    c.throw_samples = []
    for step in range(40):
        where = QPointF(float(c.min_x + 20 + step * 12), float(c.min_y + 40))
        c.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, QPointF(1.0, 1.0), where,
                                     Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
    assert c.dragging is True, "forty moves were not a drag"
    assert len(c.throw_samples) == actions.THROW_HISTORY, len(c.throw_samples)
    assert c.throw_samples[-1][1] > c.throw_samples[0][1], "the samples are not the hand"


@needs_display
def test_a_throw_never_earns_the_tug_and_a_placement_still_does(monkeypatch):
    """The precedence, both halves in one test so neither is vacuous.

    A tug drives the character along a curve at a bounded 340 px/s and carries
    the pointer by the per-frame delta; a flight integrates a velocity of up to
    2400. Starting one out of the other is the pointer being flung at
    ballistic speed, which is the single thing the carry was measured not to
    do. The negative alone would pass on a companion whose tug never fires at
    all, hence the second half.
    """
    mod, c = _companion()
    monkeypatch.setattr(type(c), "_say", lambda self, text: None)
    monkeypatch.setattr(type(c), "_snap", lambda self: None)

    def provoke(samples):
        c.recent_drags, c.drag_distance = [], 0.0
        c.tug_until, c.tugged_at = 0.0, 0.0
        c.flying = False
        c.dragging = True
        c.drag_started = time.monotonic() - (mod.DRAG_TUG_ALWAYS + 1)
        c.throw_samples = samples
        _release(c)

    provoke(_gesture(time.monotonic(), 900.0))
    assert c.flying is True, "the throw did not happen"
    assert c.tug_until == 0.0, "a throw started a tug as well"

    provoke([])
    assert c.flying is False
    assert c.tug_until > time.monotonic(), "the same provocation earned nothing"


@needs_display
def test_a_throw_calls_off_a_tug_that_was_already_running(monkeypatch):
    """The other direction of the same collision: caught mid-getaway and
    thrown, the character is in the air, and a Bézier still driving it would
    put it somewhere else on the very next frame."""
    mod, c = _companion()
    monkeypatch.setattr(type(c), "_say", lambda self, text: None)
    monkeypatch.setattr(type(c), "_snap", lambda self: None)
    now = time.monotonic()
    c.tug_until = now + 5.0
    c.tug_route = ((0.0, 0.0), (1.0, 1.0), (2.0, 2.0))
    c.recent_drags, c.drag_distance = [], 0.0
    c.drag_started = now
    c.dragging = True
    c.throw_samples = _gesture(now, 900.0)
    _release(c)
    assert c.flying is True
    assert c.tug_until == 0.0 and c.tug_route is None, "the getaway kept driving"


@needs_display
def test_the_flight_ends_and_hands_the_character_back_to_roaming():
    """A body that bounces for ever never walks again.

    And it is not docked where it lands: _snap is the answer to a placement,
    and docking a throw would end every one of them with the mascot asleep in
    whichever corner it rolled into.
    """
    mod, c = _companion()
    now = time.monotonic()
    c.pos_x = float((c.min_x + c.max_x) / 2)
    c.pos_y = float(c.min_y + 20)
    c.docked = True
    c._launch(now, (600.0, -200.0))
    assert c.flying is True

    step, elapsed = 1 / 30.0, 0.0
    while c.flying and elapsed < 30.0:
        elapsed += step
        c._fly(step, now + elapsed)
    assert not c.flying, f"still in the air after {elapsed:.0f}s"
    assert c.min_x <= c.pos_x <= c.max_x and c.min_y <= c.pos_y <= c.max_y
    assert c.docked is False, "the landing docked it"
    assert c.target == (c.pos_x, c.pos_y), "it landed still walking somewhere"
    assert c.next_move > now, "it never picked up its wandering again"


@needs_display
def test_a_bounce_plays_the_landing():
    """The impact is the frame worth animating; buddy_actions raises the flag
    on a real one and deliberately not on the every-frame contact of a body
    already lying on the floor."""
    mod, c = _companion()
    c.pos_x, c.pos_y = float(c.max_x - 1), float((c.min_y + c.max_y) / 2)
    c.vel_x, c.vel_y = 1500.0, 0.0
    c.flying = True
    c.anim.set_clip("walk")
    c._fly(1 / 30.0, time.monotonic())
    assert c.anim.clip == "land", f"hit the wall as {c.anim.clip}"


@needs_display
def test_a_hand_on_it_ends_the_flight():
    """Catching it is the end of the flight by definition, and a body still
    integrating gravity would fight the spring that follows the cursor."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    mod, c = _companion()
    c.flying = True
    c.vel_x, c.vel_y = 500.0, 500.0
    c.mousePressEvent(QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(0, 0),
                                  QPointF(500, 500), Qt.LeftButton, Qt.LeftButton,
                                  Qt.NoModifier))
    assert c.flying is False


# ── the folder dropped on it ───────────────────────────────────────────────

def _drop(companion, paths):
    """A real QDropEvent carrying local files, delivered to the widget."""
    from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
    from PySide6.QtGui import QDropEvent
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    event = QDropEvent(QPointF(1, 1), Qt.CopyAction, mime, Qt.LeftButton,
                       Qt.NoModifier)
    companion.dropEvent(event)
    return event


def _repository(tmp_path, name):
    repo = tmp_path / name
    (repo / ".git").mkdir(parents=True)
    return repo


@needs_display
def test_a_dropped_repository_becomes_one_reading(tmp_path, monkeypatch):
    """The whole point of accepting the drop: the folder becomes the working
    directory of the reading, and the resolved path at that — buddy_actions
    hands back what it checked, not the name it was given."""
    mod, c = _companion()
    asked = []
    monkeypatch.setattr(type(c), "_ask_about", lambda self, s: asked.append(s))
    repo = _repository(tmp_path, "hub")
    _drop(c, [repo])
    assert len(asked) == 1, asked
    assert asked[0]["cwd"] == os.path.realpath(repo)
    assert asked[0]["name"] == "hub"


@needs_display
@pytest.mark.parametrize("lang", ["en", "pt"])
def test_a_folder_that_is_not_a_repository_is_refused_out_loud(tmp_path, monkeypatch,
                                                               lang):
    """A drop ignored in silence is indistinguishable from one the character
    never noticed, and the person drops the same folder again."""
    mod, c = _companion()
    c.lang = lang
    said, asked = [], []
    monkeypatch.setattr(type(c), "_say", lambda self, text: said.append(text))
    monkeypatch.setattr(type(c), "_ask_about", lambda self, s: asked.append(s))
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    _drop(c, [plain])
    assert not asked, "read a directory that is not a repository"
    assert said == [c._t("dropNotARepo")], said


@needs_display
@pytest.mark.parametrize("lang", ["en", "pt"])
def test_every_rejection_reason_has_a_sentence_in_both_languages(lang):
    """buddy_actions has seven reasons and the companion is the only thing
    that can say them. One without a wording is a rejection that either says
    nothing or raises a KeyError inside a Qt event handler, which does not
    cost the drop, it costs the mascot."""
    mod, c = _companion()
    c.lang = lang
    reasons = [value for name, value in vars(actions).items()
               if name.startswith("REASON_")]
    assert len(reasons) == 7, reasons
    generic = c._t("dropRejected")
    spoken = set()
    for reason in reasons:
        text = c._drop_refusal(reason)
        assert text and text.strip(), f"{lang}/{reason} is empty"
        # Not the catch-all: that one exists for a reason this file has never
        # heard of, and a mapping quietly falling through to it would be a
        # rejection the character cannot explain — which is most of the way
        # back to saying nothing.
        assert text != generic, f"{lang}/{reason} has no wording of its own"
        spoken.add(text)
    assert len(spoken) == len(reasons), f"two reasons share a sentence: {spoken}"
    # And a reason from a newer buddy_actions than this file knows about is a
    # sentence too, rather than a KeyError.
    assert c._drop_refusal("somethingNewEntirely") == generic


@needs_display
def test_a_drop_while_it_is_already_reading_starts_nothing(tmp_path, monkeypatch):
    """One at a time, the same rule the menu has: every reading is a billed
    `claude -p`, and an impatient hand would leave six of them in flight."""
    mod, c = _companion()
    said, asked = [], []
    monkeypatch.setattr(type(c), "_say", lambda self, text: said.append(text))
    monkeypatch.setattr(type(c), "_ask_about", lambda self, s: asked.append(s))
    c.asking = object()
    _drop(c, [_repository(tmp_path, "hub")])
    assert not asked, "started a second reading while one was running"
    assert said == [c._t("dropBusy")], said


@needs_display
def test_several_folders_at_once_are_refused_rather_than_guessed(tmp_path,
                                                                 monkeypatch):
    """Reading the first of six and ignoring the rest in silence is the same
    defect the rejection lines exist to remove: from the outside it is
    indistinguishable from a drop that half worked."""
    mod, c = _companion()
    said, asked = [], []
    monkeypatch.setattr(type(c), "_say", lambda self, text: said.append(text))
    monkeypatch.setattr(type(c), "_ask_about", lambda self, s: asked.append(s))
    _drop(c, [_repository(tmp_path, "one"), _repository(tmp_path, "two")])
    assert not asked, "picked one of two on its own"
    assert said == [c._t("dropOneAtATime")], said


@needs_display
def test_the_widget_accepts_drops_and_the_enter_event_says_so(tmp_path):
    """Without setAcceptDrops the drop never arrives, and without the enter
    event there is no drop cursor over the character — which reads as a mascot
    that does not take folders."""
    from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
    from PySide6.QtGui import QDragEnterEvent
    mod, c = _companion()
    assert c.acceptDrops() is True

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(tmp_path))])
    event = QDragEnterEvent(QPoint(1, 1), Qt.CopyAction, mime, Qt.LeftButton,
                            Qt.NoModifier)
    event.ignore()
    c.dragEnterEvent(event)
    assert event.isAccepted(), "the character refused a folder before seeing it"

    plain = QMimeData()
    plain.setText("just some words")
    other = QDragEnterEvent(QPoint(1, 1), Qt.CopyAction, plain, Qt.LeftButton,
                            Qt.NoModifier)
    other.ignore()
    c.dragEnterEvent(other)
    assert not other.isAccepted(), "accepted a drag carrying no paths at all"


# ── perching on a window, and delivering a pointer to it ───────────────────

def _window(screen, minimized=False):
    return {"x": float(screen.left() + 200), "y": float(screen.top() + 200),
            "width": 800.0, "height": 600.0, "minimized": minimized,
            "pid": 4242, "caption": "session", "uuid": "u", "fullscreen": False,
            "skipTaskbar": False, "maximized": False}


def _waiting(pid=7):
    return [{"pid": pid, "name": "hub", "state": "asking", "idleSeconds": 0}]


def _climb(companion, mod, to):
    """Take the ladder from nothing to the rung named, and act on it."""
    companion.brain.sessions = {"total": 1, "attention": None,
                                "sessions": _waiting()}
    companion._insist(0.0)
    companion._insist(to + 60.0)


@needs_display
def test_the_wave_rung_perches_on_the_window_that_wants_a_human(monkeypatch):
    """Sitting on the window that is waiting says which one it is. The middle
    of the screen only says that one of them does."""
    mod, c = _companion()
    c.options = c.options._replace(insistence="wave")
    c.insistence = mod.focus_engine.Insistence(allow_pointer=False)
    screen = c.screens[0]
    window = _window(screen)
    monkeypatch.setattr(type(c), "_session_window", lambda self, pid: window)
    _climb(c, mod, mod.focus_engine.WAVE_AFTER)
    expected = actions.perch_position(window, mod.BUDDY_PX, c._corner_bounds())
    assert expected is not None, "the fixture window cannot be perched on"
    assert c.target == expected, f"{c.target} is not the perch {expected}"


@needs_display
def test_the_wave_rung_still_works_when_kwin_says_nothing(monkeypatch):
    """No busctl, no KWin, a terminal that has closed: all of them are None,
    and none of them is a reason to stop escalating."""
    mod, c = _companion()
    c.options = c.options._replace(insistence="wave")
    c.insistence = mod.focus_engine.Insistence(allow_pointer=False)
    monkeypatch.setattr(type(c), "_session_window", lambda self, pid: None)
    _climb(c, mod, mod.focus_engine.WAVE_AFTER)
    assert c.target == c._approach_target(), c.target
    assert c.insist_until > 0.0, "gave up escalating because a window was unknown"


@needs_display
def test_the_pointer_rung_aims_at_the_window_and_falls_back_without_one(monkeypatch):
    """Rung 4 is the one that takes the mouse out of somebody's hand, so where
    it puts it is the whole question. With a window it is the middle of what
    can be seen of it — never the title bar, whose right end is the close
    button. Without one it is what this rung already did."""
    mod, c = _companion()
    c.options = c.options._replace(insistence="pointer")
    c.insistence = mod.focus_engine.Insistence(allow_pointer=True)
    c.pointer = object()
    screen = c.screens[0]
    c.pos_x = float(max(c.min_x, min(c.max_x, screen.center().x())))
    c.pos_y = float(max(c.min_y, min(c.max_y, screen.center().y())))
    window = _window(screen)
    monkeypatch.setattr(type(c), "_session_window", lambda self, pid: window)
    _climb(c, mod, mod.focus_engine.POINTER_AFTER)
    expected = actions.delivery_target(window, mod.BUDDY_PX, c._corner_bounds(),
                                       (c.pos_x, c.pos_y), c._screen_rects())
    assert expected is not None, "the fixture window cannot be delivered to"
    assert c.target == expected, f"{c.target} is not the window {expected}"
    assert c.tug_route is not None and len(c.tug_route) == 3

    mod2, c2 = _companion()
    c2.options = c2.options._replace(insistence="pointer")
    c2.insistence = mod2.focus_engine.Insistence(allow_pointer=True)
    c2.pointer = object()
    monkeypatch.setattr(type(c2), "_session_window", lambda self, pid: None)
    _climb(c2, mod2, mod2.focus_engine.POINTER_AFTER)
    assert c2.tug_route is not None, "an unknown window cost the summons itself"


@needs_display
def test_the_window_lookup_never_happens_on_the_frame_path(monkeypatch):
    """buddy_actions.window_geometry blocks for 38-54 ms and worse. On the
    poll that is a fifth of the budget; on a 33 ms frame it is the character
    stopping dead, thirty times a second."""
    mod, c = _companion()
    calls = []
    monkeypatch.setattr(mod.actions, "window_geometry",
                        lambda pid, runner=None: calls.append(pid))
    c.pos_x, c.pos_y = float(c.min_x + 300), float(c.min_y + 300)
    c.target = (c.pos_x + 200, c.pos_y)
    for _ in range(10):
        c._tick()
    assert not calls, f"the frame path asked KWin for a window: {calls}"

    c.options = c.options._replace(insistence="wave")
    c.insistence = mod.focus_engine.Insistence(allow_pointer=False)
    _climb(c, mod, mod.focus_engine.WAVE_AFTER)
    assert calls, "and then the poll never asked it either"


# ── the other mascot ───────────────────────────────────────────────────────

@needs_display
def test_the_mover_walks_over_and_the_waiter_stands_still(tmp_path):
    """Two processes that both decide to approach chase each other across the
    screen; two that both decide to wait are statues. buddy_peers settles it
    from the pids alone, and the companion has to act on the side it was
    given rather than on the phase."""
    mod, c = _companion()
    now = 1000.0
    c.pos_x, c.pos_y = float(c.min_x + 100), float(c.min_y + 100)
    peer_x, peer_y = c.pos_x + 200.0, c.pos_y
    c.yard = _yard(tmp_path, mine=99, theirs=101, at=now, x=peer_x, y=peer_y)
    c.encounter = peers.Encounter()
    c._mingle(now)
    assert c.encounter.busy, "never noticed the other one"
    assert c.target[0] == pytest.approx(peer_x - mod.MEET_GAP), c.target
    assert c.target != (c.pos_x, c.pos_y)

    mod2, c2 = _companion()
    c2.pos_x, c2.pos_y = float(c2.min_x + 100), float(c2.min_y + 100)
    c2.target = (c2.pos_x + 400, c2.pos_y + 400)
    c2.yard = _yard(tmp_path / "waiter", mine=999, theirs=101, at=now,
                    x=c2.pos_x + 200.0, y=c2.pos_y)
    c2.encounter = peers.Encounter()
    c2._mingle(now)
    assert c2.encounter.busy
    assert c2.target == (c2.pos_x, c2.pos_y), "the waiter walked over as well"


@needs_display
def test_meeting_the_other_one_is_reacted_to_once(tmp_path, monkeypatch):
    """Standing next to each other satisfies the meeting condition on every
    frame. A greeting on each of them is thirty lines a second."""
    mod, c = _companion()
    said = []
    monkeypatch.setattr(type(c), "_say", lambda self, text: said.append(text))
    now = 1000.0
    c.pos_x, c.pos_y = float(c.min_x + 100), float(c.min_y + 100)
    c.yard = _yard(tmp_path, mine=99, theirs=101, brand=c.options.brand, at=now,
                   x=c.pos_x + 40.0, y=c.pos_y)
    c.encounter = peers.Encounter()
    c.facing = -1
    for frame in range(20):
        c._mingle(now + frame * 0.033)
    assert len(said) == 1, said
    assert c.target == (c.pos_x, c.pos_y), "walked off mid-conversation"
    assert c.facing == 1, "did not turn to face the other one"
    assert c.anim.clip == "nod", f"met its own kind as {c.anim.clip}"


@needs_display
def test_its_own_kind_and_the_other_provider_are_different_reactions(tmp_path,
                                                                     monkeypatch):
    """same_brand and peer.brand are exposed by buddy_peers precisely so the
    two can be told apart here. A companion that says the same thing to both
    is one that never read either field."""
    mod, c = _companion()
    said = []
    monkeypatch.setattr(type(c), "_say", lambda self, text: said.append(text))
    now = 1000.0
    c.pos_x, c.pos_y = float(c.min_x + 100), float(c.min_y + 100)
    other = "codex" if c.options.brand == "claude" else "claude"
    c.yard = _yard(tmp_path, mine=99, theirs=101, brand=other, at=now,
                   x=c.pos_x + 40.0, y=c.pos_y)
    c.encounter = peers.Encounter()
    c._mingle(now)
    assert len(said) == 1, said
    assert other in said[0], said
    assert said[0] != c._t("greetSame"), "the other provider got the family line"
    assert c.anim.clip == "shake", f"met the other one as {c.anim.clip}"


@needs_display
@pytest.mark.parametrize("state", ["docked", "tugged", "focused", "dragged"])
def test_no_encounter_while_it_is_not_where_it_says_it_is(tmp_path, state):
    """Every one of these is the same objection: the position being published
    is not where the character is going to be. Docked it was put somewhere on
    purpose; carried at 340 px/s it is four times the walking speed the notice
    radius was measured against; and a focus block is a decision not to be
    interrupted, which two mascots greeting each other in the middle of one
    plainly is."""
    mod, c = _companion()
    now = 1000.0
    c.pos_x, c.pos_y = float(c.min_x + 100), float(c.min_y + 100)
    c.yard = _yard(tmp_path, mine=99, theirs=101, at=now,
                   x=c.pos_x + 40.0, y=c.pos_y)
    c.encounter = peers.Encounter()
    if state == "docked":
        c.docked = True
    elif state == "tugged":
        c.tug_until = now + 5.0
    elif state == "focused":
        c.focus.start(now, minutes=25)
    else:
        c.dragging = True
    c._mingle(now)
    assert not c.encounter.busy, f"started an encounter while {state}"
    # And it is still visible to the other one: going quiet would make this
    # companion vanish from the directory every time it was picked up.
    assert (Path(c.yard.path) / "99.json").exists(), "stopped publishing as well"


@needs_display
def test_a_peer_that_vanishes_mid_meeting_still_releases_the_character(tmp_path):
    """buddy_peers promises one PHASE_PART per encounter and cannot always
    keep it: the peer that stops publishing — closed from its own menu, or
    killed — takes the state machine back to idle with a None and no PART at
    all. A character released only by the PART it never gets stands where the
    other one used to be until its own roaming timer comes round.
    """
    mod, c = _companion()
    now = 1000.0
    c.pos_x, c.pos_y = float(c.min_x + 100), float(c.min_y + 100)
    c.next_move = now - 1.0
    c.yard = _yard(tmp_path, mine=99, theirs=101, at=now,
                   x=c.pos_x + 40.0, y=c.pos_y)
    c.encounter = peers.Encounter()
    c._mingle(now)
    assert c.encounter.busy, "never noticed the other one"
    assert c.next_move > now, "wandered off during the conversation"

    (Path(c.yard.path) / "101.json").unlink()
    later = now + peers.READ_SECONDS + 0.1      # past the read cadence
    c._mingle(later)
    assert not c.encounter.busy, "held on to a peer that is gone"
    assert c.next_move <= later, "left standing where the other one used to be"


@needs_display
def test_the_presence_file_goes_when_the_process_does(tmp_path):
    """Without this a companion closed from its own menu stays visible to the
    other one for buddy_peers.STALE_SECONDS — five seconds of the survivor
    walking over to greet a mascot that is not there."""
    from PySide6.QtWidgets import QApplication
    mod, c = _companion()
    c.yard = _yard(tmp_path, mine=99, theirs=101, at=1000.0)
    ours = Path(c.yard.path) / "99.json"
    c._mingle(1000.0)
    assert ours.exists(), "never published in the first place"
    QApplication.instance().aboutToQuit.emit()
    assert not ours.exists(), "quitting left the file behind"

    # And the window being closed, which is not the same path: a closed window
    # does not necessarily end the process.
    from PySide6.QtGui import QCloseEvent
    c._mingle(1002.0)
    assert ours.exists()
    c.closeEvent(QCloseEvent())
    assert not ours.exists(), "closing the window left the file behind"


# ── the clips that had no trigger ──────────────────────────────────────────

@needs_display
def test_a_looping_clip_is_never_played_as_a_one_shot():
    """Animator.advance leaves a one-shot only when its frames run out, so a
    looping clip handed to play_once never ends: the character would be stuck
    in it for the rest of the session. The case is not hypothetical — it is
    what a fallback resolves to whenever the sheet has not got the pose yet,
    which is the whole reason clip_or_fallback exists.
    """
    mod, c = _companion()
    c.anim.set_clip("idle")
    c._play_once("walk")
    assert c.anim.clip == "idle", f"a loop was played as a one-shot: {c.anim.clip}"
    c._play_once("land")
    assert c.anim.clip == "land", "and then no one-shot played at all"


@needs_display
def test_the_way_into_sleep_is_a_yawn():
    """It used to cut from standing to curled up between two frames."""
    mod, c = _companion()
    now = time.monotonic()
    c.docked = True
    c.settled_at = now - mod.SLEEP_AFTER - 1
    c.anim.set_clip("idle")
    c._animate(0.02, now, moving=False)
    assert c.anim.clip == "yawn", f"fell asleep as {c.anim.clip}"
    assert c.anim.base == "sleep", "the yawn does not resume into sleeping"


@needs_display
def test_docked_against_an_edge_it_looks_over_it():
    """Parked in a corner it otherwise stands facing the wallpaper for the
    forty-five seconds before it dozes off."""
    mod, c = _companion()
    now = time.monotonic()
    c.docked = True
    c.settled_at = now
    c.pos_x, c.pos_y = float(c.min_x), float((c.min_y + c.max_y) / 2)
    c._animate(0.02, now, moving=False)
    assert c.anim.base == "peek", c.anim.base

    c.docked = False
    c.pos_x = float((c.min_x + c.max_x) / 2)
    c._animate(0.02, now, moving=False)
    assert c.anim.base != "peek", "peeked at nothing in the middle of the screen"


@needs_display
def test_a_session_at_work_is_typed_along_with():
    """The idle pose with something happening in it. Read from the sessions
    the companion is already looking at, so an escort narrows this too."""
    mod, c = _companion(poll=True)
    now = time.monotonic()
    c.brain.refresh = lambda: None
    c.brain.sessions = {"total": 1, "attention": None, "sessions": [
        {"pid": 7, "name": "hub", "state": "working", "idleSeconds": 0}]}
    c.brain.line = lambda now=None, wall=None: None
    c._poll()
    assert c.working is True
    c._animate(0.02, now, moving=False)
    assert c.anim.base == "type", c.anim.base

    c.brain.sessions = {"total": 0, "attention": None, "sessions": []}
    c._poll()
    assert c.working is False
    c._animate(0.02, now, moving=False)
    assert c.anim.base == "idle", c.anim.base


@needs_display
def test_turning_round_is_animated_rather_than_mirrored():
    """A sprite replaced by its own mirror image between two frames is the
    oldest tell there is. And it has a floor under it: the getaway recomputes
    the facing every frame, and a route that doubles back would replay the
    turn on every flip."""
    mod, c = _companion()
    now = time.monotonic()
    c.facing, c._faced, c._turned_at = 1, 1, 0.0
    c.anim.set_clip("walk")
    c.facing = -1
    c._animate(0.02, now, moving=True)
    assert c.anim.clip == "turn", f"turned as {c.anim.clip}"
    turned_at = c._turned_at

    # A flip a frame and a half later, which is what a route doubling back
    # produces. The delay is an absolute number rather than a fraction of the
    # constant under test: computed from it, a floor of zero would still be
    # "inside the floor" and the check would watch nothing.
    c.facing = 1
    c._animate(0.02, now + 0.05, moving=True)
    assert c._turned_at == turned_at, "replayed the turn inside its own floor"
    c.facing = -1
    c._animate(0.02, now + mod.TURN_MIN_GAP + 0.1, moving=True)
    assert c._turned_at > turned_at, "never turned again at all"


@needs_display
@pytest.mark.parametrize("key,clip", [
    ("quotaCritical", "panic"),
    ("creditsLow", "panic"),
    ("allQuiet", "celebrate"),
    ("cacheDrop", ""),
    ("ambient", ""),
])
def test_the_mood_of_a_line_reaches_the_sprite(key, clip):
    """The sentence and the pose are one statement. Which lines get one is
    read off buddy_signals' priority band rather than listed here, so a signal
    added to the band arrives with the pose already attached."""
    mod, c = _companion(poll=True)
    assert mod.Companion._mood_for(key) == clip

    c.brain.refresh = lambda: None
    c.brain.sessions = {"total": 0, "attention": None, "sessions": []}

    def line(now=None, wall=None):
        c.brain.spoke = key
        return f"a line about {key}"
    c.brain.line = line
    c._poll()
    assert c.mood_clip == clip, c.mood_clip
    if clip:
        assert c.mood_until > time.monotonic()
        c._animate(0.02, time.monotonic(), moving=False)
        assert c.anim.base == clip, c.anim.base


@needs_qt
def test_every_clip_in_the_sheet_has_something_that_triggers_it():
    """The twoRed lesson, applied to the art.

    A clip nothing selects is drawn, tested, shipped and never once seen —
    the same defect as a category of dialogue no code can reach, which this
    project has already paid for once. The scan deliberately ignores
    CLIP_FALLBACK: being named there is what a clip is worth *instead of*, not
    a way of reaching it.
    """
    mod = _load()
    source = re.sub(r"CLIP_FALLBACK = \{.*?\}", "", COMPANION.read_text(),
                    flags=re.S)
    named = {name for name in mod.sprites.CLIPS if f'"{name}"' in source}
    # blink is the one exception, and it is not an exception to the rule: the
    # Animator fires it itself, from maybe_blink, which the companion calls on
    # every frame.
    missing = set(mod.sprites.CLIPS) - named - {"blink"}
    assert not missing, f"clips nothing can reach: {sorted(missing)}"


@needs_qt
@pytest.mark.parametrize("fragment", [
    "actions.throw_velocity(", "actions.integrate(",
    "actions.dropped_repositories(", "actions.perch_position(",
    "actions.delivery_target(", "actions.window_geometry(",
    "actions.THROW_HISTORY", "actions.REASON_",
    "peers.PeerDirectory(", "peers.Encounter(",
    "peers.PHASE_APPROACH", "peers.PHASE_PART", "peers.ROLE_MOVER",
    "self.yard.publish(", "self.yard.peers(", "self.yard.retire()",
    "self.encounter.update(", "self.encounter.busy",
])
def test_the_modules_are_used_and_not_merely_imported(fragment):
    """Both modules were written, tested, and reachable from nothing.

    An import on its own is exactly what that looked like from the outside,
    which is why this checks the calls rather than the import line: every
    public entry point of the two has to be reached from the companion, or
    the part of them that is not reached is the part that has never run on a
    desktop.
    """
    assert fragment in COMPANION.read_text(), f"{fragment} is never reached"


@needs_display
def test_the_self_test_still_prints_its_json_and_exits_zero():
    """The installation gate. It is also where a mascot already running on
    this desktop could hijack the walk under test, by publishing a position
    the self-test would walk over to."""
    import subprocess
    result = subprocess.run([sys.executable, str(COMPANION), "--self-test"],
                            capture_output=True, text=True, timeout=60,
                            env={**os.environ, "QT_QPA_PLATFORM": "xcb"})
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert set(report) == {"movedX", "movedY", "geometry", "frameMs"}, report
    assert report["movedX"] > 10 and report["movedY"] > 10, report
