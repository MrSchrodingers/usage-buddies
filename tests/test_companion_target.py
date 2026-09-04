"""The target on the desktop, the record that outlives the process, the rally.

buddy_target has its own suite and it is pure arithmetic — no Qt, no clock, no
window. Every assertion here is about the companion reaching it, drawing its
answer and acting on it, which is the half that was missing: the module and the
art both shipped tested and green while nothing on any desktop put a target on
a screen. That is the `twoRed` defect, and this project has paid for it once.

Five seams, and what each one costs when the wiring is wrong.

A third always-on-top window 144 by 140 that is not transparent to the *input
region* swallows every click that lands inside it. WA_TransparentForMouseEvents
is not enough on a separate top level and the operator has already lost the
ability to click the mascot to exactly that mistake, so what is asserted here
is the region the X server reports and never the attribute that was supposed to
empty it.

A window hung by the middle of its own rectangle drops the bullseye five source
pixels below whatever it was aimed at, because the target hangs from a hook and
its rings are not centred on its canvas. Nothing about that looks like a bug.

A radius converted twice is a target that is one size to look at and another
size to hit. target_rings() and target_centre() are the only conversion there
is, and a second multiplication anywhere in the companion is invisible until
somebody notices the game feels arbitrary.

A hit judged against this frame's position instead of against the travel misses
every throw fast enough to be worth aiming: the physics moves the body up to
118 px in one integration step, which is wider than the whole face.

And a record that is not written when it is set is not a record. It is a number
that resets the next time the machine is rebooted.
"""
import contextlib
import importlib.util
import json
import math
import os
import stat
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
COMPANION = REPO / "scripts" / "usage-buddy-companion.py"

sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))
import buddy_actions as actions           # noqa: E402
import buddy_hoop                         # noqa: E402
import buddy_sprites as sprites           # noqa: E402
import buddy_target as target_game        # noqa: E402

# The instrument, borrowed rather than written again. It reads the input region
# off the X server with XShapeGetRectangles, which is the only reading that
# answers the question somebody actually has — whether the click reaches what
# is underneath — and it was written for the basket after a version of this
# check that asserted the attribute shipped a false claim.
from test_companion_hoop import _x_input_rectangles   # noqa: E402

needs_display = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None or not os.environ.get("DISPLAY"),
    reason="PySide6 or X display missing")


def _load(name="companion_target"):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    spec = importlib.util.spec_from_file_location(name, COMPANION)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _companion(mod=None):
    """A Companion with both timers stopped, so the test owns the clock."""
    mod = mod or _load()
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    c = mod.Companion()
    c.poll_timer.stop()
    c.frame_timer.stop()
    c._poll = lambda: None
    c._mingle = lambda *_a: None
    return mod, c


def _quiet(c, monkeypatch):
    """No bubble and no docking: both are somebody else's test."""
    monkeypatch.setattr(type(c), "_say", lambda self, text: None)
    monkeypatch.setattr(type(c), "_snap", lambda self: None)


def _heard(c, monkeypatch):
    """Every sentence this companion says, in order."""
    said = []
    monkeypatch.setattr(type(c), "_say", lambda self, text: said.append(text))
    monkeypatch.setattr(type(c), "_snap", lambda self: None)
    return said


def _no_windows(mod, monkeypatch):
    """No third top-level window put up on the operator's own desktop.

    The suite builds Companions on the same machine a real mascot is running
    on. A test that shows the character and drives a throw to its end offers a
    target, and an offered target is shown — which is a 144x140 window
    appearing over somebody's editor and staying there. `appear` is the one
    call that maps it, so that is what is stubbed; it doubles as the record of
    where the drawing was hung. Everything else about the window is exercised
    by the tests that build one deliberately.

    The companion's own refusal to offer anything while it is not on screen is
    the belt to this pair of braces, and has a test of its own — but a stub
    here is what keeps a mistake in that guard from costing the operator a
    window rather than a red test.
    """
    shown = []
    monkeypatch.setattr(mod.TargetWindow, "appear",
                        lambda self, centre: shown.append(centre))
    return shown


@contextlib.contextmanager
def _on_screen(c):
    """The character actually shown, which is what a target hangs off.

    A companion nobody has shown offers no game: its window is wherever it was
    constructed rather than where the character is standing, and an offer made
    there would put a 144x140 always-on-top window on the desktop of whoever is
    running the suite. So a test of the offer has to show the character, and
    hide it again — three of them do, for a fraction of a second each, and
    every other test in this file never puts anything on screen at all.
    """
    c.show()
    try:
        yield c
    finally:
        c.hide()


def _gesture(now, speed=900.0, samples=4, step=0.03):
    """A drag whose last 90 ms happened at `speed` px/s, going right.

    Built rather than driven through real events, for the reason
    test_companion_actions gives: two mouse events a millisecond apart divided
    into three pixels is a launch on any machine, and proves nothing about the
    threshold.
    """
    return [(now - (samples - 1 - i) * step, 400.0 + i * step * speed, 300.0)
            for i in range(samples)]


def _release_at(c, where):
    """A left-button release carrying an explicit global position.

    The four-point constructor is not optional. MEASURED, and recorded in
    test_companion_hoop: the short QMouseEvent(type, localPos, ...) derives the
    global position from the desktop's own pointer, so a test written with it
    asserts against wherever the operator's mouse happens to be sitting.
    """
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    point = QPointF(float(where[0]), float(where[1]))
    c.mouseReleaseEvent(QMouseEvent(QMouseEvent.MouseButtonRelease,
                                    QPointF(0.0, 0.0), QPointF(0.0, 0.0), point,
                                    Qt.LeftButton, Qt.NoButton, Qt.NoModifier))


def _press_at(c, where):
    """A left-button press carrying an explicit global position."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    point = QPointF(float(where[0]), float(where[1]))
    c.mousePressEvent(QMouseEvent(QMouseEvent.MouseButtonPress,
                                  QPointF(0.0, 0.0), QPointF(0.0, 0.0), point,
                                  Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))


def _hands_off(c):
    """Everything a release reads, back to the state of never having been
    touched — except the game, which is what these tests are about."""
    c.flying = False
    c.chasing = False
    c.chase_until = 0.0
    c.recent_drags = []
    c.drag_distance = 0.0
    c.tug_until = 0.0
    c.tugged_at = 0.0
    c.tug_route = None


def _throw(c, where=(600.0, 400.0)):
    """One release fast enough to be a throw."""
    _hands_off(c)
    now = time.monotonic()
    c.dragging = True
    c.drag_started = now
    c.throw_samples = _gesture(now)
    _release_at(c, where)


def _put_down(c, where=(600.0, 400.0)):
    """One release slow enough to be a placement, and provocative in no other
    way: held for no time, moved no distance, and no drag remembered."""
    _hands_off(c)
    now = time.monotonic()
    c.dragging = True
    c.drag_started = now
    c.throw_samples = []
    _release_at(c, where)


def _inside(c, dx=200.0, dy=200.0):
    """A point comfortably inside the walking area, as a global position."""
    return (float(c.min_x + dx), float(c.min_y + dy))


def _put_target(c, now, where=None):
    """A target at a known place, built the way place_target builds one.

    Constructed rather than placed, because place_target samples an rng
    fourteen times and a test that threw at its answer would be a test of the
    random number generator. The rings are the art's own, converted once, which
    is the only conversion in the program.
    """
    rings = target_game.target_rings()
    assert rings, "the art declares no rings; there is nothing to aim at"
    if where is None:
        where = (float(c.min_x + 500), float(c.min_y + 400))
    c.throws.target = target_game.Target(where[0], where[1], rings, now)
    return c.throws.target


# ── the window is scenery ──────────────────────────────────────────────────

@needs_display
def test_a_click_goes_straight_through_the_target():
    """The effect, read off the X server, and never the mechanism.

    This is the defect that reached the operator: a frameless always-on-top
    overlay carrying WA_TransparentForMouseEvents and nothing else reports one
    input rectangle and swallows every click inside it, and he could no longer
    click the mascot at all. The attribute governs Qt's hit testing inside an
    application; on a separate top level the X input region is left alone.
    Qt.WindowTransparentForInput is what empties it, and the region is what is
    asserted here — a check that reads the flag would pass on a window that
    takes every click, which is exactly how the last one shipped.

    This drawing is 144x140, larger than the overlay that did it.
    """
    mod = _load()
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    if app.platformName() != "xcb":
        pytest.skip("no X display: the input region cannot be read here")

    window = mod.TargetWindow()
    window.show()
    app.processEvents()
    try:
        rectangles = _x_input_rectangles(int(window.winId()))
        if rectangles is None:
            pytest.skip("libX11/libXext unavailable")
        assert rectangles == 0, (
            "the target registered %d input rectangle(s); the server will "
            "deliver clicks to it instead of to what is underneath"
            % rectangles)
    finally:
        window.close()


@needs_display
def test_the_target_window_has_no_second_way_in():
    """The flag is what does it, and a mouse handler would be scenery acting on
    input whatever the flags say. Both are wanted; neither is the proof above."""
    mod = _load()
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    window = mod.TargetWindow()
    assert window.windowFlags() & mod.Qt.WindowTransparentForInput, \
        "the target is in front of everything and the server will give it clicks"
    assert window.testAttribute(mod.Qt.WA_TransparentForMouseEvents), \
        "the attribute is not sufficient on its own but it is still wanted"
    handlers = sorted(name for name in vars(mod.TargetWindow)
                      if name.startswith(("mouse", "wheel", "tablet")))
    assert not handlers, f"the target handles input: {handlers}"


@needs_display
def test_the_target_hangs_by_its_rings_and_not_by_its_rectangle():
    """The drawing hangs from a hook: twelve rows above the disc and two below.

    A window placed by the middle of its own image drops the bullseye five
    source pixels — ten screen pixels — below the point the game scored the
    throw against. Nothing about that reads as a bug; it reads as a target that
    is oddly hard to hit, which is the reason target_centre() exists at all.

    The tolerance is the scale and not zero because place() snaps to the
    drawing's grid, which is deliberate: a sprite on half a source pixel does
    not look blurry, it looks like it is crawling.
    """
    mod = _load()
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    window = mod.TargetWindow()
    spot = target_game.target_centre()
    assert spot is not None, "the art declares no centre"
    dx, dy = spot

    aim = (1000.0, 800.0)
    window.place(aim)
    assert abs(window.x() + dx - aim[0]) <= window.scale, \
        "the middle of the rings did not land on the point it was aimed at"
    assert abs(window.y() + dy - aim[1]) <= window.scale, \
        "the middle of the rings did not land on the point it was aimed at"

    # And it is not the middle of the rectangle, or the assertion above would
    # hold for a window hung by its corner and prove nothing.
    assert abs(dy - window.height() / 2.0) > window.scale, (
        "the rings are centred on the canvas after all, so hanging the window "
        "by its rectangle would look identical and this test is vacuous")


@needs_display
def test_the_rings_are_drawn_and_scored_at_one_scale_and_only_one():
    """Converted twice, every radius is doubled and the offset with it.

    A target scored against radii the art never drew is not a visible defect —
    the drawing is the same picture either way — it is a game that feels
    arbitrary. So the window carries no scale of its own: buddy_target does the
    single conversion and the window is drawn at that scale, which is what
    makes the two impossible to disagree.
    """
    mod = _load()
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    window = mod.TargetWindow()
    rings = target_game.target_rings()
    assert rings, "no rings to check"

    assert window.scale == sprites.SCALE, \
        "the drawing is at a scale buddy_target did not convert with"
    assert window.width() == sprites.TARGET_W * window.scale
    assert window.height() == sprites.TARGET_H * window.scale
    assert rings[-1].radius == sprites.TARGET_RINGS[-1][0] * window.scale, \
        "the outer ring is scored at a size the art was not drawn at"
    # The window's own offset is buddy_target's answer, passed through. A
    # second multiplication here would put it outside the image entirely.
    assert window.centre == target_game.target_centre()
    assert 0 < window.centre[0] < window.width()
    assert 0 < window.centre[1] < window.height()
    assert rings[-1].radius * 2 <= window.width(), \
        "the scoring area is wider than the drawing it is scored against"


@needs_display
def test_no_target_frame_is_ever_handed_to_the_character_s_animator():
    """sprites.Animator resolves names against CLIPS, which is the character's
    sheet. A target frame looked up there resolves to nothing, and a clip name
    that reaches it raises inside the frame timer, which is the process.

    The other direction is the twoRed guard: a clip drawn, tested and named by
    nothing is art that renders in no session.
    """
    mod = _load()
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    window = mod.TargetWindow()

    for frame in window.sheet:
        assert frame not in sprites.CLIPS, \
            f"{frame} is on the target's sheet and in the character's clips"
    source = COMPANION.read_text()
    unreachable = [name for name in sprites.TARGET_CLIPS
                   if f'"{name}"' not in source]
    assert not unreachable, f"target clips nothing plays: {unreachable}"

    window.play("hit")
    frames = [f for f, _ms in sprites.TARGET_CLIPS["hit"]["frames"]]
    assert window.frame == frames[0], window.frame
    seen = {window.frame}
    for _ in range(200):
        window.advance(0.02)
        seen.add(window.frame)
    assert seen >= set(frames), f"never reached {set(frames) - seen}"
    assert window.frame == mod.TARGET_RESTING, "the one-shot looped"


@needs_display
def test_a_hit_plays_the_targets_own_clip_and_the_characters_own_pose(
        monkeypatch):
    """The source scan above says the name exists somewhere in the file; this
    says it arrives, and at the right window. The target's clip goes to the
    target's sheet and the character's pose goes through clip_or_fallback,
    which is the guard that keeps a pose the art has not drawn yet from being
    looked up on every frame inside the animator."""
    mod, c = _companion()
    _quiet(c, monkeypatch)
    _no_windows(mod, monkeypatch)
    played = []
    monkeypatch.setattr(mod.TargetWindow, "play",
                        lambda self, name: played.append(name))
    now = time.monotonic()
    half = mod.BUDDY_PX / 2.0

    c._target_ready()                # the window exists to be played
    target = _put_target(c, now)
    cx, cy = target.centre
    c.pos_x, c.pos_y = cx - 4.0 - half, cy - half
    c.vel_x, c.vel_y = 8.0, 0.0
    c.flying = True
    c._fly(1 / 60.0, now)

    assert c.throws.hits == 1, "nothing was hit, so nothing was played"
    assert played, "the target was hit and its drawing said nothing"
    for name in played:
        assert name in sprites.TARGET_CLIPS, \
            f"{name} is not a clip on the target's own sheet"
    assert c.mood_clip in sprites.CLIPS, \
        f"{c.mood_clip} reaches the animator and is not one of its clips"
    assert c.target_hide_at > now, \
        "the drawing is hidden before its own clip can finish"


# ── when the target goes up ────────────────────────────────────────────────

@needs_display
def test_the_target_waits_for_the_flight_that_would_have_scored_it_to_end(
        monkeypatch):
    """A settled throw no longer puts a target up at all, and the flight is
    where that used to happen.

    It was the reward for the provoking act: a live target suspends the
    getaway, so throwing repeatedly kept re-arming the suspension the throwing
    was supposed to earn. Summoning is a deliberate menu action now. The
    original guard is kept in the first half — a target must never appear
    around a body already in the air, because then aiming is optional — and
    the second half asserts the new contract."""
    mod, c = _companion()
    _quiet(c, monkeypatch)
    shown = _no_windows(mod, monkeypatch)
    now = time.monotonic()

    with _on_screen(c):
        _throw(c)
        assert c.flying is True, "the throw did not happen"
        assert c.throws.live(now) is False, \
            "a target appeared around a live throw"
        assert shown == []

        for frame in range(1, 400):
            c._fly(1 / 60.0, now + frame / 60.0)
            if not c.flying:
                break
        assert c.flying is False, "never came down"
        later = time.monotonic()
        assert c.throws.live(later) is False, \
            "the flight put a target up; only the menu may do that now"
        assert shown == [], "a drawing appeared without anyone asking for one"

        # And the menu still works, hung where the game scores.
        c._target_summon()
        assert c.throws.live(time.monotonic()) is True, \
            "the menu asked for a target and none went up"
        assert len(shown) == 1, f"the drawing was shown {len(shown)} times"
        assert shown[0] == c.throws.target.centre, \
            "the drawing was hung somewhere the game does not score"


@needs_display
def test_a_placement_puts_no_target_up(monkeypatch):
    """Setting the character down on the desktop is not asking for a game, and
    buddy_target answers a release under the throw floor by saying so — but it
    can only answer a release it was told about. Told about the throws alone it
    goes on holding the last throw's force band, and the next time the
    character is put down it offers a target for a gesture that was not one.
    That is the defect this pins, and the throw has to come first for it to be
    reachable at all.

    What this does NOT pin, measured rather than assumed: a companion that
    reports no release whatsoever also passes here, because then the throw sets
    no force band either and the offer is refused for the other reason. The
    seam being present at all is pinned by
    test_the_target_waits_for_the_flight_that_would_have_scored_it_to_end and
    by test_catching_it_in_the_air_twice_is_a_rally. A test that claims more
    than it holds is worse than one that claims less.
    """
    mod, c = _companion()
    _quiet(c, monkeypatch)
    _no_windows(mod, monkeypatch)
    now = time.monotonic()

    with _on_screen(c):
        _throw(c, _inside(c))
        _put_down(c, _inside(c))
        c._target_settled(now, (c.pos_x, c.pos_y))
        assert c.throws.live(now) is False, "putting it down summoned a target"


@needs_display
def test_a_character_nobody_has_shown_offers_no_game(monkeypatch):
    """The guard that keeps this suite off the operator's desktop, and it is
    not only a test convenience: buddy_target says a scoring area with nothing
    drawn in it is worse than no game at all, so a character that is not on
    screen does not offer one rather than offering an invisible one.

    Without it, every test anywhere in this suite that drives a throw to its
    end — and test_companion_hoop has one — leaves a 144x140 always-on-top
    window on the desktop of whoever ran it.
    """
    mod, c = _companion()
    _quiet(c, monkeypatch)
    shown = _no_windows(mod, monkeypatch)
    now = time.monotonic()
    assert c.isVisible() is False, "the fixture showed the character"

    _throw(c)
    c._target_settled(now, (c.pos_x, c.pos_y))
    assert shown == [], "a window was put up for a character nobody can see"
    assert c.target_window is None, "a window was built for nothing to be in"
    assert c.throws.live(now) is False, \
        "an invisible target was put up and it can still be scored"


@needs_display
def test_the_basket_is_what_the_target_is_kept_clear_of(monkeypatch):
    """The two games are on screen together on purpose, and the only thing that
    must not happen is one drawn on top of the other. buddy_target takes an
    `avoid` for it and the companion is the only thing that knows there is a
    basket at all."""
    mod, c = _companion()
    _quiet(c, monkeypatch)
    _no_windows(mod, monkeypatch)
    now = time.monotonic()

    basket = c.game.offer(now, buddy_hoop.HOOP_AFTER, (c.pos_x, c.pos_y),
                          c._screen_rects())
    assert basket is not None, "no basket to keep clear of"

    seen = []
    real = target_game.place_target

    def spy(position, screens, sprite_px, rings, at, rng, avoid=()):
        seen.append(list(avoid))
        return real(position, screens, sprite_px, rings, at, rng, avoid)

    monkeypatch.setattr(mod.target_game, "place_target", spy)
    with _on_screen(c):
        # Through the menu, which is the only door now.
        c._target_summon()

    assert seen, "no target was ever placed"
    kept_clear = seen[-1]
    assert kept_clear, "the basket was not passed; the two can be drawn on top"
    assert any(abs(spot[0] - basket.centre[0]) < 1.0
               and abs(spot[1] - basket.centre[1]) < 1.0
               for spot in kept_clear), (kept_clear, basket.centre)
    # With a size, not as a bare point. place_target keeps the new target clear
    # by `radius + other + sprite`, so a basket passed as a point of no size is
    # a basket the target may be drawn half on top of. What the geometry then
    # does with the number is buddy_target's, and has its own suite; what is
    # this end's is that the number is the drawn opening's.
    assert all(len(spot) > 2 for spot in kept_clear), kept_clear
    assert any(abs(spot[2] - basket.rim / 2.0) < 1.0 for spot in kept_clear), \
        (kept_clear, basket.rim)


# ── the throw is scored against the travel ─────────────────────────────────

@needs_display
def test_a_throw_that_crosses_the_whole_face_in_one_step_still_scores(
        monkeypatch):
    """The tunnel, which is the defect that makes aiming pointless.

    MEASURED against this physics: buddy_actions clamps a step to MAX_STEP =
    0.05 s, and at 2400 px/s that is 118 px of travel in one integration step.
    The whole face is 112 px across. The body starts 59 px to the left of the
    middle and ends 59 px to the right of it, so on both of the two positions a
    frame can see it, it is outside the outer ring — and it passed through the
    bullseye.

    Judged on the current position alone this scores nothing, and the throws it
    would miss are exactly the ones somebody aimed.
    """
    mod, c = _companion()
    _quiet(c, monkeypatch)
    _no_windows(mod, monkeypatch)
    now = time.monotonic()
    half = mod.BUDDY_PX / 2.0

    target = _put_target(c, now)
    cx, cy = target.centre
    assert target.radius <= 59.0 < 118.0, (
        "the geometry this is built on moved: %s" % (target.radius,))

    c.pos_x, c.pos_y = cx - 59.0 - half, cy - half
    c.vel_x, c.vel_y = float(actions.THROW_MAX_SPEED), 0.0
    c.flying = True
    before = (c.pos_x, c.pos_y)
    c._fly(actions.MAX_STEP, now)

    travelled = c.pos_x - before[0]
    assert travelled > 2 * target.radius, (
        "the step was %.1f px and the face is %.1f across, so nothing was "
        "jumped over and this test proves nothing"
        % (travelled, 2 * target.radius))
    for spot in (before, (c.pos_x, c.pos_y)):
        near = ((spot[0] + half - cx) ** 2 + (spot[1] + half - cy) ** 2) ** 0.5
        assert near > target.radius, (
            "the body was on the target at one end of the step, so a frame "
            "that only looked at where it is would have scored it too")
    assert c.throws.hits == 1, "the throw went clean through the target"
    assert c.throws.points >= target.rings[0].points, \
        "a throw through the middle was paid at the edge's rate"


@needs_display
def test_the_middle_is_worth_more_than_the_edge_and_says_so(monkeypatch):
    """The rings are a promise the drawing makes without a legend, and a
    bullseye answered with the same sentence as the outer band is the drawing
    lying. What is checked is the sentence and the score together: either alone
    passes on a companion that says one thing and pays another."""
    mod, c = _companion()
    now = time.monotonic()
    half = mod.BUDDY_PX / 2.0
    said = _heard(c, monkeypatch)
    _no_windows(mod, monkeypatch)

    target = _put_target(c, now)
    cx, cy = target.centre
    edge = target.rings[-1].radius - 1.0
    # Through the edge of the outer band, moving slowly enough that the segment
    # stays out there for the whole step.
    c.pos_x, c.pos_y = cx - 4.0 - half, cy + edge - half
    c.vel_x, c.vel_y = 8.0, 0.0
    c.flying = True
    c._fly(1 / 60.0, now)
    assert c.throws.hits == 1, "a body on the outer band scored nothing"
    edge_points = c.throws.points
    edge_line = said[-1]

    said.clear()
    target = _put_target(c, now, (cx, cy))
    c.pos_x, c.pos_y = cx - 4.0 - half, cy - half
    c.vel_x, c.vel_y = 8.0, 0.0
    c._fly(1 / 60.0, now)
    assert c.throws.hits == 2, "a body on the bullseye scored nothing"
    bull_points = c.throws.points - edge_points

    assert bull_points > edge_points, (bull_points, edge_points)
    assert said[-1] != edge_line, \
        "the middle and the edge are answered with the same sentence"


@needs_display
def test_three_in_a_row_is_a_run_and_not_three_hits(monkeypatch):
    """A third sentence, because the third hit is the first that cannot be
    luck. A companion that only ever congratulates the hit in front of it makes
    the combo buddy_target keeps a number nobody is ever told."""
    mod, c = _companion()
    now = time.monotonic()
    half = mod.BUDDY_PX / 2.0
    said = _heard(c, monkeypatch)
    _no_windows(mod, monkeypatch)

    lines = []
    for _ in range(3):
        target = _put_target(c, now)
        cx, cy = target.centre
        c.pos_x, c.pos_y = cx - 4.0 - half, cy - half
        c.vel_x, c.vel_y = 8.0, 0.0
        c.flying = True
        c._fly(1 / 60.0, now)
        lines.append(said[-1])

    assert c.throws.hits == 3, "three throws through the middle scored %d" \
        % c.throws.hits
    assert c.throws.combo.run(now) == 3, "the run was not kept"
    assert lines[2] != lines[1], \
        "the third in a row was answered like any other hit"


@needs_display
def test_a_target_nobody_threw_at_and_one_that_was_missed_are_two_sentences(
        monkeypatch):
    """The counter is what tells them apart, and they are two different things
    to say: one is nobody playing, the other is somebody playing badly. Said
    once, on the frame it runs out, and not once per frame for as long as
    nothing is up."""
    mod, c = _companion()
    said = _heard(c, monkeypatch)
    _no_windows(mod, monkeypatch)
    c.frame_timer.setInterval(mod.FRAME_MS_ACTIVE)
    now = time.monotonic()

    _put_target(c, now)
    c.target_tries_at = c.throws.state(now).misses
    c.throws.target.shown_at = now - target_game.TARGET_SECONDS - 1.0
    said.clear()
    c._target_tick(time.monotonic(), 0.033)
    ignored = list(said)
    assert len(ignored) == 1, ignored
    c._target_tick(time.monotonic(), 0.033)
    assert said == ignored, "the sentence repeated once the target was gone"

    # And now the same expiry with a throw counted against it.
    now = time.monotonic()
    _put_target(c, now)
    c.target_tries_at = c.throws.state(now).misses
    c.throws.misses += 1
    c.throws.target.shown_at = now - target_game.TARGET_SECONDS - 1.0
    said.clear()
    c._target_tick(time.monotonic(), 0.033)
    assert len(said) == 1, said
    assert said[0] != ignored[0], \
        "a target that was thrown at and one that was ignored say the same thing"


@needs_display
def test_the_record_is_the_throw_and_it_survives_the_process(monkeypatch,
                                                             tmp_path):
    """A longest throw that resets at every login is not a record.

    buddy_target keeps the number and does no I/O at all — it says so — so the
    file is the companion's, and the moment it is written is the moment the
    number changes. Written on a timer instead, the last throw of every session
    that ends with the machine sleeping is lost.

    The cache under test is the one conftest hands every test, and that is
    asserted rather than assumed: this suite runs on the same machine a real
    mascot is running on, and a test that wrote into the operator's own cache
    would be putting a record he did not earn on his desktop.
    """
    mod, c = _companion()
    _quiet(c, monkeypatch)
    _no_windows(mod, monkeypatch)
    assert str(mod.CACHE).startswith(str(tmp_path.parent.parent)) or \
        "pytest" in str(mod.CACHE), \
        f"the record would be written into a real cache: {mod.CACHE}"
    assert mod.RECORDS_FILE.name == "companion-records.json"
    assert mod.RECORDS_FILE.parent == mod.CACHE

    now = time.monotonic()
    c._target_released(now, (100.0, 100.0), (900.0, -300.0))
    c._target_settled(now, (700.0, 100.0))

    assert mod.RECORDS_FILE.exists(), "the record was never written"
    saved = json.loads(mod.RECORDS_FILE.read_text())
    mine = saved[c.options.brand]
    assert abs(mine["best_px"] - 600.0) < 1.0, saved
    mode = stat.S_IMODE(mod.RECORDS_FILE.stat().st_mode)
    assert mode == 0o600, oct(mode)
    assert not [p for p in mod.RECORDS_FILE.parent.glob("*.tmp")], \
        "a temporary was left behind beside the record"

    # And the next process starts from it rather than from zero.
    assert target_game.Record.from_dict(c._read_record()).best \
        == pytest.approx(mine["best_px"])


@needs_display
def test_the_other_mascot_s_record_is_not_taken_from_it(monkeypatch):
    """Two mascots on one desktop is a configuration this program supports —
    buddy_peers opens by saying so and companion-ctl.sh starts one per brand —
    and they share one cache directory. One flat number in a file both of them
    write is the claude mascot's long throw silently replaced by whatever the
    codex one did last, which is data the operator earned and can only get back
    by earning it again.

    So the record is keyed by brand, and the entry that is not this character's
    is carried across rather than dropped. What is left is a race between two
    of the same brand, which is a race and not a certainty.
    """
    mod, c = _companion()
    _quiet(c, monkeypatch)
    _no_windows(mod, monkeypatch)
    other = "codex" if c.options.brand == "claude" else "claude"
    mod.RECORDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    mod.RECORDS_FILE.write_text(json.dumps({other: {"best_px": 1200.0}}))

    now = time.monotonic()
    c._target_released(now, (100.0, 100.0), (900.0, -300.0))
    c._target_settled(now, (400.0, 100.0))          # 300 px, a shorter throw

    saved = json.loads(mod.RECORDS_FILE.read_text())
    assert saved[other]["best_px"] == 1200.0, \
        f"the other mascot's record was overwritten: {saved}"
    assert abs(saved[c.options.brand]["best_px"] - 300.0) < 1.0, saved
    # And this character does not inherit the other one's number either.
    assert c.throws.record.best == pytest.approx(300.0)


@needs_display
def test_a_record_that_cannot_be_saved_is_a_record_lost_and_not_a_dead_mascot(
        monkeypatch, tmp_path):
    """A full disk, a read-only cache, a directory somebody chmod'ed. None of
    them is worth the character, and this is reached from the frame timer by
    way of _fly — where an exception is the process and not the frame."""
    mod, c = _companion()
    _quiet(c, monkeypatch)
    _no_windows(mod, monkeypatch)
    wall = tmp_path / "wall"
    wall.write_text("not a directory")
    monkeypatch.setattr(mod, "RECORDS_FILE", wall / "companion-records.json")

    now = time.monotonic()
    c._target_released(now, (100.0, 100.0), (900.0, -300.0))
    c._target_settled(now, (700.0, 100.0))          # must not raise
    assert c.throws.record.best == pytest.approx(600.0), \
        "the record was lost in memory as well as on disk"
    assert c.target_enabled is True, \
        "an unwritable cache turned the game off"


@needs_display
def test_closing_the_character_takes_the_target_down_with_it(monkeypatch):
    """The window is transparent to input and has no mouse handler and no menu.
    Left on the desktop by a character that has gone, there is no way to close
    it but killing the process — the operator's own word for that failure mode,
    about the last overlay, was that he could not click the mascot.

    The list this used to be was written when there were two windows and the
    target was added without it. So it is not a list any more, and what is
    asserted is the rule rather than the three names: every top-level window
    this object put up goes when the character does.
    """
    mod, c = _companion()
    _quiet(c, monkeypatch)
    c._target_ready()
    c._hoop_ready()
    c._halo_ready()
    scenery = c.scenery()
    assert len(scenery) >= 3, \
        f"the sweep found {len(scenery)} windows and three were built"
    assert c.target_window in scenery, "the target is not counted as scenery"
    for window in scenery:
        window.show()
    from PySide6.QtWidgets import QApplication
    QApplication.instance().processEvents()
    assert all(w.isVisible() for w in scenery), "nothing was up to take down"

    try:
        c.close()
        still_up = [type(w).__name__ for w in scenery if w.isVisible()]
        assert not still_up, \
            f"left on the desktop with nothing under them: {still_up}"
    finally:
        for window in scenery:
            window.hide()


@needs_display
def test_junk_in_the_records_file_starts_at_zero_rather_than_not_at_all(
        monkeypatch):
    """The file is state the program wrote for itself. Refusing to start
    because it was truncated by a full disk is a worse bug than losing a number
    that can be re-earned by throwing the character across the screen."""
    mod, c = _companion()
    mod.RECORDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    junk = ("", "{", "[1, 2, 3]", '"a string"',
            # And the two shapes that are legal JSON in the right place and
            # still not a record: the brand's entry is not a mapping, and it is
            # a mapping whose number is not one.
            '{"%s": "far"}' % c.options.brand,
            '{"%s": {"best_px": "far"}}' % c.options.brand,
            '{"best_px": 900.0}')          # the old flat shape, before brands
    for text in junk:
        mod.RECORDS_FILE.write_text(text)
        record = target_game.Record.from_dict(c._read_record())
        assert record.best == 0.0, f"{text!r} became {record.best}"
        # And building a whole companion off it is a companion, not a traceback.
        mod.Companion().close()
    mod.RECORDS_FILE.unlink()
    assert c._read_record() == {}


# ── the rally ──────────────────────────────────────────────────────────────

@needs_display
def test_catching_it_in_the_air_twice_is_a_rally(monkeypatch):
    """Thrown, caught in mid-air, thrown again. The catch itself already
    worked — the press ends the flight — and what was missing was the verdict.

    The second catch and not the first: one catch is somebody stopping a throw,
    and a rally that congratulates itself on being interrupted is noise.
    """
    mod, c = _companion()
    said = _heard(c, monkeypatch)
    _no_windows(mod, monkeypatch)

    _throw(c)
    assert c.flying is True
    c.vel_x, c.vel_y = 900.0, -300.0
    _press_at(c, _inside(c))
    now = time.monotonic()
    assert c.throws.juggle.run(now) == 1, "the catch was not counted"
    assert not [line for line in said if "1" in line], \
        "one catch was announced as a rally"

    _throw(c)
    c.vel_x, c.vel_y = 900.0, -300.0
    _press_at(c, _inside(c))
    now = time.monotonic()
    assert c.throws.juggle.run(now) == 2, "the second catch was not counted"
    assert said and "2" in said[-1], said


@needs_display
def test_picking_it_up_off_the_floor_is_not_a_catch(monkeypatch):
    """A body that has bounced below the speed it could lift itself with is
    hopping, not flying, and scooping it up there would make the whole rally
    free — a rally could be kept alive by letting the character roll to a stop
    and then picking it up, which is the opposite of the skill it counts.

    What tells the two apart is the speed each impact left behind, and the
    impacts happen inside the physics: the companion is the only thing that can
    report them. Both halves are here, because the second alone would pass on a
    companion whose rally never counts anything at all.
    """
    mod, c = _companion()
    _quiet(c, monkeypatch)
    _no_windows(mod, monkeypatch)

    # Caught on the arc it was thrown on. Nothing has hit it yet.
    _throw(c)
    c.vel_x, c.vel_y = 900.0, -300.0
    _press_at(c, _inside(c))
    assert c.throws.juggle.run(time.monotonic()) == 1, \
        "a catch in clean air was not counted"

    # And the same hand, on the same character, after the bounces have taken
    # it below the speed it can lift itself with.
    _throw(c)
    c.pos_x = float(c.min_x + 400)
    c.pos_y = float(c.max_y - 300)
    c.vel_x, c.vel_y = 0.0, 700.0
    c.flying = True
    now = time.monotonic()
    for frame in range(1, 600):
        c._fly(1 / 60.0, now + frame / 60.0)
        if not c.flying or not c.throws.juggle.airborne():
            break
    assert c.flying is True, (
        "the flight ran all the way to a stop without the rally ever hearing "
        "about an impact, so nothing in it could tell a catch from a scoop")
    assert c.throws.juggle.airborne() is False, \
        "no impact was ever reported, so every scoop is a catch"
    speed = math.hypot(c.vel_x, c.vel_y)
    assert speed < target_game.lift_speed(mod.BUDDY_PX), \
        f"still doing {speed:.0f} px/s, which is a body in the air"

    _press_at(c, _inside(c))
    assert c.throws.juggle.run(time.monotonic()) == 0, \
        "a scoop off the floor counted as a catch"


# ── what the two games agree about ─────────────────────────────────────────

@needs_display
def test_the_getaway_waits_while_a_target_is_up(monkeypatch):
    """Retaliating in the middle of a game the character is playing withdraws
    the offer, which is the game dying on the third throw. Suspension only: the
    temper is untouched, so the moment the target is gone the character is
    exactly as angry as it was, and the basket is still the one thing that
    forgives it."""
    mod, c = _companion()
    _quiet(c, monkeypatch)
    _no_windows(mod, monkeypatch)
    now = time.monotonic()

    _throw(c)
    _throw(c)
    assert c.game.should_chase(now) is True, "two throws were not remembered"
    _put_target(c, now)

    def held_far_too_long():
        _hands_off(c)
        c.dragging = True
        c.drag_started = time.monotonic() - (mod.DRAG_TUG_ALWAYS + 1)
        c.throw_samples = []
        _release_at(c, _inside(c))
        return c.chasing or c.tug_until > time.monotonic()

    assert not held_far_too_long(), "took the mouse with the target still up"
    c.throws.target.shown_at = now - target_game.TARGET_SECONDS - 1.0
    assert c.throws.suspends_getaway(time.monotonic()) is False
    assert held_far_too_long(), "the target expired and the getaway went with it"
    # And nothing about the target ever forgave the throws.
    assert c.game.state(time.monotonic()).angry is True, \
        "the target cleared the temper; only the basket may do that"


@needs_display
def test_the_getaway_waits_for_a_rally_to_be_over_too(monkeypatch):
    """A rally ends the only way it can end — the character is put down — and
    that same release is the one the getaway fires on.

    Every catch and every throw of a rally goes into recent_drags, so the
    release that ends a five-catch rally arrives already past DRAG_TUG_AFTER.
    Ask the game about the rally *after* telling it about the placement and it
    answers honestly that there is none: the placement is what ended it. The
    character then runs off with the mouse for having been played with, which
    is the game dying on the third throw — the exact thing buddy_target says
    the suspension exists to prevent.

    So the order inside the release is the behaviour, and this is what pins it.
    """
    mod, c = _companion()
    _quiet(c, monkeypatch)
    _no_windows(mod, monkeypatch)

    # A rally: thrown, caught, thrown, caught. Four releases and two catches,
    # which is enough recent_drags to have provoked the getaway on its own.
    for _ in range(3):
        _throw(c)
        c.vel_x, c.vel_y = 900.0, -300.0
        _press_at(c, _inside(c))
    now = time.monotonic()
    assert c.throws.juggle.run(now) >= 2, "no rally to interrupt"
    assert c.throws.suspends_getaway(now) is True, "the rally is not live"
    assert c.throws.live(now) is False, \
        "a target is up, so this would pass on the target's suspension alone"

    # And now it is put down, which is the one way a rally ends.
    drags = list(c.recent_drags)
    c.dragging = True
    c.drag_started = time.monotonic() - (mod.DRAG_TUG_ALWAYS + 1)
    c.throw_samples = []
    c.recent_drags = drags
    _release_at(c, _inside(c))
    assert c.chasing is False and c.tug_until == 0.0, \
        "took the mouse for the release that ended the rally"
    # The rally is over — the placement ended it, which is buddy_target's rule
    # and not in question — and the next provocation is answered as usual.
    assert c.throws.juggle.run(time.monotonic()) == 0, \
        "putting it down left the rally standing"


@needs_display
def test_a_game_that_failed_suspends_nothing(monkeypatch):
    """The getaway is the character's and a toy must not be able to disarm it.
    A failure inside the target game turns the target off; it does not buy
    permanent immunity from being answered."""
    mod, c = _companion()
    _quiet(c, monkeypatch)
    now = time.monotonic()
    _put_target(c, now)
    assert c._target_suspends(now) is True

    class Broken:
        def suspends_getaway(self, _now):
            raise RuntimeError("the toy broke")

        def clear(self):
            pass

    c.throws = Broken()
    assert c._target_suspends(now) is False
    assert c.target_enabled is False, "a raising game was left armed"


@needs_display
def test_a_failure_on_the_frame_path_stops_the_game_and_not_the_mascot(
        monkeypatch):
    """A raise inside a QTimer slot is the process, not the frame. The answer
    to one is to stop playing rather than to raise thirty times a second until
    the mascot disappears — which is what the operator would see."""
    mod, c = _companion()
    _quiet(c, monkeypatch)

    class Broken:
        def expired(self, _now):
            raise RuntimeError("the toy broke")

        def clear(self):
            pass

    c.throws = Broken()
    c.frame_timer.setInterval(mod.FRAME_MS_ACTIVE)
    c._tick()                                   # must not raise
    assert c.target_enabled is False, "the game went on raising"
    c._tick()                                   # and stays off


@needs_display
def test_the_target_is_disarmed_where_nobody_is_watching():
    """--self-test runs on a desktop somebody is using, to answer one question
    about whether the mascot walks. A third always-on-top window left behind by
    a throwaway process is the one thing it must not do."""
    source = COMPANION.read_text()
    block = source[source.index("if options.self_test:"):]
    for switch in ("hoop_enabled = False", "halo_enabled = False",
                   "target_enabled = False"):
        assert switch in block, f"--self-test does not set {switch}"
