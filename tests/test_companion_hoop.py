"""Being thrown twice, the basket offered instead, and the run at the pointer.

buddy_hoop has its own suite and it is pure arithmetic; every assertion here is
about the companion reaching it and acting on the answer. Three seams, and what
each one costs when the wiring is wrong.

A throw that is not counted is the regression this undoes: the release path
answered a throw by suppressing the whole retaliation, so the one gesture that
most obviously deserves an answer was the one gesture guaranteed not to get
one. A run that starts anywhere but on the pointer ends with the pointer
displaced by exactly the gap it started with, because the carry moves it by the
character's own per-frame delta and never by an absolute position. And a
192x144 always-on-top window that is not transparent to the mouse swallows
every click that lands on it, which is a defect wearing the costume of a game.
"""
import importlib.util
import os
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
COMPANION = REPO / "scripts" / "usage-buddy-companion.py"

sys.path.insert(0, str(REPO / "scripts"))
import buddy_hoop                          # noqa: E402
import buddy_sprites as sprites            # noqa: E402

needs_display = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None or not os.environ.get("DISPLAY"),
    reason="PySide6 or X display missing")


def _load(name="companion_hoop"):
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

    The four-point constructor is not optional here. MEASURED: the short
    QMouseEvent(type, localPos, ...) does not copy the local position into the
    global one — it derives the global one from the desktop's own pointer, so
    (1234, 567) came back as (2662, 808) on this machine. A test written with
    it asserts against wherever the operator's mouse happens to be sitting.
    """
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    point = QPointF(float(where[0]), float(where[1]))
    c.mouseReleaseEvent(QMouseEvent(QMouseEvent.MouseButtonRelease,
                                    QPointF(0.0, 0.0), QPointF(0.0, 0.0), point,
                                    Qt.LeftButton, Qt.NoButton, Qt.NoModifier))


def _quiet(c, monkeypatch):
    """No bubble and no docking: both are somebody else's test."""
    monkeypatch.setattr(type(c), "_say", lambda self, text: None)
    monkeypatch.setattr(type(c), "_snap", lambda self: None)


def _hands_off(c):
    """Everything a release reads, back to the state of never having been
    touched — except the temper, which is what these tests are about."""
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


class _Middle:
    """An rng that always answers with the middle of the range.

    buddy_hoop.place_hoop takes one so the basket's position is a test's to
    decide. Without it the basket is somewhere random on the screen and a test
    that throws at it is a test of the random number generator.
    """

    @staticmethod
    def random():
        return 0.5

    @staticmethod
    def choice(options):
        return options[0]


def _offer(c, now):
    """Put a basket up at the middle of the character's screen."""
    return c.game.offer(now, buddy_hoop.HOOP_AFTER, (c.pos_x, c.pos_y),
                        c._screen_rects(), rng=_Middle)


# ── the temper ─────────────────────────────────────────────────────────────

@needs_display
def test_one_throw_is_a_joke_and_two_are_an_answer(monkeypatch):
    """The regression, both halves in one test so neither is vacuous.

    The negative alone would pass on a companion whose temper never fires, and
    the positive alone would pass on one that comes for the mouse the first
    time it is picked up. What is being checked is that the throw is what feeds
    it: no drag here is long enough, far enough or repeated enough to earn the
    getaway on its own.
    """
    mod, c = _companion()
    _quiet(c, monkeypatch)

    _throw(c)
    _put_down(c, _inside(c))
    assert c.chasing is False and c.tug_until == 0.0, \
        "one throw came for the pointer"

    _throw(c)
    _put_down(c, _inside(c))
    assert c.chasing is True, "thrown twice and it did nothing about it"


@needs_display
def test_the_throw_itself_still_never_starts_the_getaway(monkeypatch):
    """The precedence inside one release is unchanged: a tug drives the
    character along a Bézier at a bounded 340 px/s while a flight integrates up
    to 2400, and the pointer is carried by the per-frame delta of whichever is
    moving it. What changed is that the throw is now remembered instead of
    forgiven."""
    mod, c = _companion()
    _quiet(c, monkeypatch)

    _throw(c)
    _throw(c)
    assert c.flying is True, "the second throw did not happen"
    assert c.chasing is False and c.tug_until == 0.0, \
        "the throw that caused the anger also acted on it"
    assert c.game.should_chase(time.monotonic()) is True, \
        "two throws were not remembered"


# ── the run at the pointer ─────────────────────────────────────────────────

@needs_display
def test_the_run_goes_to_the_position_the_release_carried(monkeypatch):
    """Not QCursor.pos(), and the two releases are what prove it.

    MEASURED on the desktop this was written for: QCursor.pos() reads
    XWayland's shadow of the pointer, and the shadow stops following the
    pointer while it is over a native Wayland window. A companion that ran at
    that reading would run at where an X client last saw the cursor. Two
    releases at two different positions cannot both be answered from one
    query, however fresh that query looks.
    """
    from PySide6.QtCore import QPoint
    mod, c = _companion()
    _quiet(c, monkeypatch)
    # And poisoned outright, so reading it is a wrong answer rather than a
    # coincidence: this is the far corner of the walking area and no release
    # below is anywhere near it.
    monkeypatch.setattr(mod.QCursor, "pos",
                        staticmethod(lambda: QPoint(int(c.max_x), int(c.max_y))))

    _throw(c)
    _throw(c)
    half = mod.BUDDY_PX / 2.0
    for where in (_inside(c, 240.0, 180.0), _inside(c, 700.0, 320.0)):
        c.chasing = False
        _put_down(c, where)
        assert c.chasing is True, f"never ran at {where}"
        assert abs(c.target[0] - (where[0] - half)) < 1.0, (c.target, where)
        assert abs(c.target[1] - (where[1] - half)) < 1.0, (c.target, where)


@needs_display
def test_a_reading_it_cannot_vouch_for_skips_the_leg_and_keeps_the_getaway(
        monkeypatch):
    """A refusal costs the alignment and nothing else.

    The staleness ceiling is moved rather than the function stubbed, so the
    path under test is the one that runs on a desktop: buddy_hoop answers None
    for every reading it cannot date, and None means the run is skipped and the
    getaway starts from where the character stands, which is the behaviour that
    shipped before any of this existed.
    """
    mod, c = _companion()
    _quiet(c, monkeypatch)
    monkeypatch.setattr(mod.buddy_hoop, "CURSOR_STALE_AFTER", -1.0)

    _throw(c)
    _throw(c)
    _put_down(c, _inside(c))
    assert c.chasing is False, "ran at a reading it had just refused"
    assert c.tug_until > time.monotonic(), "the getaway was lost with the leg"


@needs_display
def test_arriving_hands_the_run_over_to_the_carry(monkeypatch):
    """The second leg. A run that arrives and stops there is a character that
    walked over to look at your cursor."""
    mod, c = _companion()
    _quiet(c, monkeypatch)
    _throw(c)
    _throw(c)
    _put_down(c, _inside(c, 400.0, 300.0))
    assert c.chasing is True

    # Standing on it: the walk has nowhere left to go.
    c.pos_x, c.pos_y = c.target
    c.frame_timer.setInterval(mod.FRAME_MS_ACTIVE)
    c._tick()
    assert c.chasing is False, "still chasing after it arrived"
    assert c.tug_until > time.monotonic(), "arrived and never took the pointer"
    assert c.tug_route is not None


@needs_display
def test_the_run_is_read_as_anger_and_moves_like_it(monkeypatch):
    """The scowl and the speed are the whole of what says this is not a walk."""
    mod, c = _companion()
    _quiet(c, monkeypatch)
    now = time.monotonic()
    c.dragging = c.docked = c.flying = False
    c.bubble = ""
    c.alert_until = 0.0
    c.insist_clip = ""
    c.mood_until = 0.0
    c.chasing = True
    c._animate(0.02, now, moving=True)
    assert c.anim.base == "furious", f"ambled over: {c.anim.base}"

    # And the distance it covers in a second is the getaway's, not the walk's.
    c.chase_until = now + mod.CHASE_SECONDS
    c.chase_seconds = 5.0
    c.pos_x, c.pos_y = float(c.min_x + 100), float(c.min_y + 100)
    c.target = (float(c.max_x), c.pos_y)
    before = c.pos_x
    c.frame_timer.setInterval(mod.FRAME_MS_ACTIVE)
    c._tick()
    step = c.pos_x - before
    assert step > mod.WALK_SPEED * 0.033 + 1, \
        f"crossed {step:.1f}px in a frame, which is a stroll"


@needs_display
def test_picking_it_up_mid_run_ends_the_run(monkeypatch):
    """The leg is aimed at where the pointer was at the last release. A hand on
    the character makes that reading old, and finishing the run afterwards is a
    sprint to somewhere the pointer has had all the time in the world to leave.
    """
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    mod, c = _companion()
    _quiet(c, monkeypatch)
    _throw(c)
    _throw(c)
    _put_down(c, _inside(c, 400.0, 300.0))
    assert c.chasing is True

    c.mousePressEvent(QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(0.0, 0.0),
                                  QPointF(0.0, 0.0), QPointF(*_inside(c)),
                                  Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    assert c.chasing is False, "kept running with a hand on it"
    assert c.tug_until == 0.0, "took the pointer anyway"


@needs_display
def test_the_setting_that_refuses_the_pointer_refuses_the_run_at_it(monkeypatch):
    """`off` reads as leave me alone, and a lunge at the cursor that ends in a
    carry which is not allowed to happen is the same promise broken one step
    earlier."""
    mod, c = _companion()
    _quiet(c, monkeypatch)
    c.options = c.options._replace(insistence="off")
    _throw(c)
    _throw(c)
    _put_down(c, _inside(c))
    assert c.chasing is False and c.tug_until == 0.0 and c.tug_route is None


# ── the basket ─────────────────────────────────────────────────────────────

@needs_display
def test_the_basket_suspends_the_getaway_and_expiring_gives_it_back(monkeypatch):
    """It is an offer: throw me at that instead. Retaliating while it is up
    withdraws the offer before anybody could accept it — and it expiring is
    what stops holding the button down from being a way never to be retaliated
    against at all."""
    mod, c = _companion()
    _quiet(c, monkeypatch)
    now = time.monotonic()
    _throw(c)
    _throw(c)
    assert _offer(c, now) is not None, "no basket went up"

    _put_down(c, _inside(c))
    assert c.chasing is False and c.tug_until == 0.0, \
        "took the mouse with the basket still up"

    # Twelve seconds later, unscored.
    c.game.hoop.shown_at = now - buddy_hoop.HOOP_SECONDS - 1.0
    _put_down(c, _inside(c))
    assert c.chasing is True, "the basket expired and the anger went with it"


@needs_display
def test_the_basket_suspends_the_drag_retaliation_as_well(monkeypatch):
    """And this half is the companion's own, not buddy_hoop's.

    should_chase folds the suspension into the answer it gives about the
    temper, so a test that only throws twice proves that module's arithmetic
    and not this file's wiring. The tiers that come from being *held* are the
    ones the gate here covers, and they are not incidental: the basket goes up
    at six seconds of holding and the tier that fires every time is at ten, so
    the two overlap by design. While the offer is on screen the hold is
    answered with the offer.
    """
    mod, c = _companion()
    _quiet(c, monkeypatch)
    now = time.monotonic()
    assert _offer(c, now) is not None, "no basket went up"

    def held_far_too_long():
        _hands_off(c)
        c.dragging = True
        c.drag_started = time.monotonic() - (mod.DRAG_TUG_ALWAYS + 1)
        c.throw_samples = []
        _release_at(c, _inside(c))
        return c.chasing or c.tug_until > time.monotonic()

    assert not held_far_too_long(), "took the mouse with the basket still up"
    c.game.hoop.shown_at = now - buddy_hoop.HOOP_SECONDS - 1.0
    assert held_far_too_long(), "the basket expired and the getaway went with it"


@needs_display
def test_scoring_pays_the_temper_off_and_missing_does_not(monkeypatch):
    """Playing along is the way out, and it is the only one. A miss that
    forgave a throw would make the game a way of working the anger off by
    throwing more, which is the opposite of what it is for."""
    mod, c = _companion()
    _quiet(c, monkeypatch)
    now = time.monotonic()
    _throw(c)
    _throw(c)
    assert c.game.should_chase(now) is True

    hoop = _offer(c, now)
    assert hoop is not None
    cx, cy = hoop.centre
    half = mod.BUDDY_PX / 2.0
    # A short throw from one side, which lands before gravity has taken it
    # below the ring: 150 px at 900 px/s is a sixth of a second.
    c.pos_x, c.pos_y = cx - 150.0 - half, cy - half
    c._launch(now, (900.0, -160.0))
    for frame in range(1, 60):
        c._fly(1 / 60.0, now + frame / 60.0)
        if c.game.state(now).score:
            break
    state = c.game.state(now)
    assert state.score == 1, f"the throw went straight through: {state}"
    assert state.misses == 0
    assert c.game.should_chase(now) is False, "scored and stayed furious"
    assert c.mood_clip == mod.clip_or_fallback("celebrate")

    # And the anger it was carrying is gone, not deferred.
    _put_down(c, _inside(c))
    assert c.chasing is False and c.tug_until == 0.0


@needs_display
def test_a_flight_that_ends_beside_the_basket_is_a_miss(monkeypatch):
    """The counter is what tells a basket nobody tried from one nobody hit,
    and those are two different sentences."""
    mod, c = _companion()
    _quiet(c, monkeypatch)
    now = time.monotonic()
    hoop = _offer(c, now)
    assert hoop is not None
    # Along the bottom of the screen, which is nowhere near the ring.
    c.pos_x, c.pos_y = float(c.min_x + 40), float(c.max_y)
    c._launch(now, (400.0, 0.0))
    for frame in range(1, 200):
        c._fly(1 / 60.0, now + frame / 60.0)
        if not c.flying:
            break
    assert c.flying is False, "never came down"
    state = c.game.state(now)
    assert state.score == 0 and state.misses == 1, state


# ── the basket on the screen ───────────────────────────────────────────────

@needs_display
def test_the_drawing_and_the_hit_area_are_measured_at_the_same_scale():
    """Drawn at one scale and judged at another, the basket is one size to
    look at and another size to hit, and the only symptom is that it feels
    wrong. Drawn at 3 while the hit area converts HOOP_RIM with SCALE = 2, the
    opening is 114 px across and a throw has to pass within 76 of the middle:
    a basket that looks generous and plays like an exam.
    """
    mod = _load()
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    window = mod.HoopWindow()
    rim = buddy_hoop.rim_width()
    assert rim is not None, "no opening to convert"
    assert sprites.HOOP_RIM[2] * window.scale == rim, (
        f"the drawing is scaled by {window.scale} and the hit area by "
        f"{rim / sprites.HOOP_RIM[2]:g}")
    assert window.width() == sprites.HOOP_W * window.scale
    assert window.height() == sprites.HOOP_H * window.scale


@needs_display
def test_the_window_is_hung_by_its_opening_and_not_by_its_corner():
    """The point buddy_hoop scores a throw against is the middle of the hole.
    A window placed by its own centre puts the hole somewhere else, and the
    player aims at a picture that is not the target."""
    mod = _load()
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    window = mod.HoopWindow()
    centre = (900.0, 540.0)
    window.place(centre)
    ox, oy = window.opening
    assert abs(window.x() + ox - centre[0]) <= window.scale, window.x()
    assert abs(window.y() + oy - centre[1]) <= window.scale, window.y()


@needs_display
def test_a_click_goes_straight_through_the_basket():
    """It is scenery. A frameless always-on-top window of this size that took
    the mouse would swallow every click that landed inside it, and what is
    under it is somebody's work.

    Asserted on the attribute, and that is a decision rather than a shortcut.
    WA_TransparentForMouseEvents is the mechanism — Qt turns it into an empty
    X input region, and the click is then delivered to whatever is underneath
    by the server rather than by us. MEASURED here, end to end, on a desktop
    that was cooperating at the time: with the attribute set,
    QApplication.widgetAt over the middle of the shown window answered None;
    with it cleared, the same call answered the window itself.

    That measurement is *not* what this test does by default, for two
    reasons. The instrument is not dependable on a desktop the suite does not
    own: measured again an hour later on the same machine, widgetAt could not
    see a plain opaque QWidget anywhere on the screen, because it resolves
    through the compositor's stacking and anything above our window turns a
    true answer into None. And the positive control it needs is a window that
    *does* eat clicks, put on somebody's live desktop for as long as the probe
    takes — a suite that swallows a click of the operator's to prove that the
    product does not is a bad trade. So it is opt-in, and it checks its own
    control before it believes its answer.
    """
    mod = _load()
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QPoint
    app = QApplication.instance() or QApplication([])

    window = mod.HoopWindow()
    assert window.testAttribute(mod.Qt.WA_TransparentForMouseEvents), \
        "the basket is in front of everything and it eats clicks"
    # And there is no second way in. A handler on this class would be a mouse
    # event acted on by scenery, whatever the attribute says.
    handlers = sorted(name for name in vars(mod.HoopWindow)
                      if name.startswith(("mouse", "wheel", "tablet")))
    assert not handlers, f"the basket handles input: {handlers}"

    if not os.environ.get("BUDDY_CLICK_PROBE"):
        pytest.skip("set BUDDY_CLICK_PROBE=1 to show windows on this desktop")

    def _seen(widget, limit=2.0):
        deadline = time.monotonic() + limit
        found = None
        while time.monotonic() < deadline:
            app.processEvents()
            found = QApplication.widgetAt(
                QPoint(widget.x() + widget.width() // 2,
                       widget.y() + widget.height() // 2))
            if found is not None:
                break
        return found

    control = mod.HoopWindow()
    control.setAttribute(mod.Qt.WA_TransparentForMouseEvents, False)
    control.appear((900.0, 540.0))
    try:
        visible_to_the_probe = _seen(control) is control
    finally:
        control.hide()
        app.processEvents()
    if not visible_to_the_probe:
        pytest.skip("widgetAt cannot see its own control on this desktop")

    window.appear((900.0, 540.0))
    try:
        assert _seen(window) is None, \
            "a click on the basket stops at the basket"
    finally:
        window.hide()
        app.processEvents()


@needs_display
def test_the_score_clip_is_walked_here_because_the_animator_cannot(monkeypatch):
    """sprites.Animator resolves names against CLIPS, which is the character's
    sheet; a hoop frame looked up there resolves to nothing. And a clip nothing
    plays is drawn, tested, shipped and never once seen."""
    mod = _load()
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    window = mod.HoopWindow()
    unreachable = [name for name in sprites.HOOP_CLIPS
                   if f'"{name}"' not in COMPANION.read_text()]
    assert not unreachable, f"hoop clips nothing plays: {unreachable}"

    window.play("score")
    frames = [frame for frame, _ms in sprites.HOOP_CLIPS["score"]["frames"]]
    assert window.frame == frames[0], window.frame
    seen = {window.frame}
    for _ in range(200):
        window.advance(0.02)
        seen.add(window.frame)
    assert seen >= set(frames), f"never reached {set(frames) - seen}"
    assert window.frame == mod.HOOP_RESTING, "the one-shot looped"


# ── the basket on the frame path ───────────────────────────────────────────

@needs_display
def test_holding_it_puts_a_basket_up_once_and_says_so_once(monkeypatch):
    mod, c = _companion()
    said = []
    monkeypatch.setattr(type(c), "_say", lambda self, text: said.append(text))
    shown = []
    monkeypatch.setattr(mod.HoopWindow, "appear",
                        lambda self, centre: shown.append(centre))
    now = time.monotonic()
    c.dragging = True
    c.drag_started = now - buddy_hoop.HOOP_AFTER - 0.1

    c._hoop_tick(now, 0.033)
    assert shown, "held well past the offer and no basket went up"
    assert c.game.live(now) is True
    assert said == [c._t("hoopUp")], said

    c._hoop_tick(now + 0.033, 0.033)
    assert len(shown) == 1 and len(said) == 1, "said it again on the next frame"


@needs_display
def test_the_frame_the_companion_runs_on_is_what_reaches_the_game(monkeypatch):
    """Every other test here calls the game's own frame method. If the frame
    timer never calls it, all of them pass and no basket has ever appeared on
    a desktop, which is the exact shape of the defect this file exists for."""
    mod, c = _companion()
    monkeypatch.setattr(type(c), "_say", lambda self, text: None)
    shown = []
    monkeypatch.setattr(mod.HoopWindow, "appear",
                        lambda self, centre: shown.append(centre))
    c.hand = (float(c.pos_x), float(c.pos_y))
    c.dragging = True
    c.drag_started = time.monotonic() - buddy_hoop.HOOP_AFTER - 0.1
    c.frame_timer.setInterval(mod.FRAME_MS_ACTIVE)
    c._tick()
    assert shown, "a whole frame went by and the game was never asked"


@needs_display
def test_a_basket_nobody_threw_at_expires_with_a_different_line(monkeypatch):
    mod, c = _companion()
    said = []
    monkeypatch.setattr(type(c), "_say", lambda self, text: said.append(text))
    monkeypatch.setattr(mod.HoopWindow, "appear", lambda self, centre: None)
    now = time.monotonic()
    c.dragging = True
    c.drag_started = now - buddy_hoop.HOOP_AFTER - 0.1
    c._hoop_tick(now, 0.033)
    c.dragging = False

    c.game.hoop.shown_at = now - buddy_hoop.HOOP_SECONDS - 1.0
    c._hoop_tick(now, 0.033)
    assert said[-1] == c._t("hoopGone"), said
    c._hoop_tick(now + 0.1, 0.033)
    assert said.count(c._t("hoopGone")) == 1, "kept announcing it every frame"


@needs_display
def test_a_basket_that_was_thrown_at_expires_with_the_other_one(monkeypatch):
    """The two are not the same event and they do not get the same sentence."""
    mod, c = _companion()
    said = []
    monkeypatch.setattr(type(c), "_say", lambda self, text: said.append(text))
    monkeypatch.setattr(mod.HoopWindow, "appear", lambda self, centre: None)
    now = time.monotonic()
    c.dragging = True
    c.drag_started = now - buddy_hoop.HOOP_AFTER - 0.1
    c._hoop_tick(now, 0.033)
    c.dragging = False

    c.game.missed()
    c.game.hoop.shown_at = now - buddy_hoop.HOOP_SECONDS - 1.0
    c._hoop_tick(now, 0.033)
    assert said[-1] == c._t("hoopMissed"), said


@needs_display
def test_the_game_switching_itself_off_costs_the_game_and_not_the_process():
    """This runs inside a QTimer slot. An exception there does not lose a
    frame, it ends the mascot."""
    mod, c = _companion()
    c._hoop_frame = lambda now, dt: (_ for _ in ()).throw(RuntimeError("no window"))
    c._hoop_tick(time.monotonic(), 0.033)
    assert c.hoop_enabled is False, "kept trying, thirty times a second"


@needs_display
def test_the_switch_the_self_test_throws_stops_the_basket(monkeypatch):
    """--self-test runs where nobody is watching, and a second always-on-top
    window put up by a throwaway process is the one thing it must not leave
    behind on somebody's desktop."""
    mod, c = _companion()
    monkeypatch.setattr(type(c), "_say", lambda self, text: None)
    shown = []
    monkeypatch.setattr(mod.HoopWindow, "appear",
                        lambda self, centre: shown.append(centre))
    c.hoop_enabled = False
    now = time.monotonic()
    c.dragging = True
    c.drag_started = now - buddy_hoop.HOOP_AFTER - 0.1
    c._hoop_tick(now, 0.033)
    assert not shown and c.hoop_window is None
    assert c.game.live(now) is False

    source = COMPANION.read_text()
    assert "companion.hoop_enabled = False" in source, \
        "the switch exists and --self-test does not throw it"


@needs_display
@pytest.mark.parametrize("fragment", [
    "buddy_hoop.HoopGame(", "buddy_hoop.rim_width()", "buddy_hoop.chase_target(",
    "self.game.thrown(", "self.game.should_chase(", "self.game.offer(",
    "self.game.landed(", "self.game.missed()", "self.game.live(",
    "self.game.expired(", "self.game.clear()", "self.game.state(",
    "self.game.suspends_getaway(",
])
def test_the_module_is_used_and_not_merely_imported(fragment):
    """buddy_hoop was written, tested and reachable from nothing, which is what
    this project has already paid for twice. An import on its own looks exactly
    like that from the outside, so this checks the calls."""
    assert fragment in COMPANION.read_text(), f"{fragment} is never reached"
