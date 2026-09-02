"""Being thrown twice, and the basket offered instead of retaliation.

Each test here is one way the gag goes wrong. It fires on the first throw, so
putting the character down once takes the mouse away. It forgets the basket
and takes the mouse in the middle of offering an alternative. It puts the
basket somewhere unreachable — on top of the character, half off a screen, or
in one of the regions of the union of two monitors that belongs to no display
at all. It misses the throw it was built for, because the flight is integrated
in steps of up to MAX_STEP and a fast throw is on one side of the rim on one
frame and past it on the next. And it runs at a reading of the pointer that
XWayland stopped updating, which is a sprint to where the cursor used to be.

Time is an argument throughout, so none of this sleeps.
"""
import ast
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import buddy_hoop as hoop

# The sprite as the companion builds it: buddy_sprites.GRID 28 at SCALE 2.
SPRITE = 56
# A stand-in for buddy_sprites.HOOP_RIM, which is the art's number and is
# never repeated in the module under test — it arrives as a parameter, so a
# test can hand in any width and the hit area has to follow it.
RIM = 40.0

# MEASURED on the desktop this was written for, and quoted in buddy_actions:
# KWin and Qt both report HDMI-A-1 at (0, 0, 2194, 1234) and eDP-1 at
# (2195, 0, 1920, 1200). The two heights differ, which is what puts regions
# inside the union of the pair that belong to no monitor.
LEFT_SCREEN = (0, 0, 2194, 1234)
RIGHT_SCREEN = (2195, 0, 1920, 1200)
SCREENS = [LEFT_SCREEN, RIGHT_SCREEN]

# The companion's own bounds for that desktop: the union, inset by 8 px and by
# the sprite on the right and bottom, exactly as Companion.min_x .. max_y are.
BOUNDS = (8, 8, 4115 - SPRITE - 8, 1234 - SPRITE - 8)


def _inside(rect, x, y):
    left, top, width, height = rect
    return left <= x < left + width and top <= y < top + height


def _companion_constant(name):
    """A module-level number out of the companion, without importing Qt.

    Read from the source rather than by import: the companion pulls in PySide6
    at module scope and this file must run on a machine with no display. It
    raises rather than returning a default, so a renamed constant fails here
    instead of quietly passing a comparison against nothing.
    """
    source = (REPO / "scripts" / "usage-buddy-companion.py").read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is no longer a constant of the companion")


# ── the temper ──

def test_one_throw_is_not_a_provocation():
    """Throwing it once is the discovery that it can be thrown. A character
    that takes the mouse for that punishes the first thing anybody tries."""
    temper = hoop.Temper()
    assert temper.thrown(1000.0) == 1
    assert not temper.furious(1000.0)
    assert not temper.furious(1000.0 + hoop.THROW_MEMORY - 1)


def test_two_throws_inside_the_window_earn_the_getaway():
    """More than once is a decision, and that is the whole trigger."""
    temper = hoop.Temper()
    temper.thrown(1000.0)
    assert temper.thrown(1000.0 + 5.0) == 2
    assert temper.furious(1000.0 + 5.0)


def test_two_throws_further_apart_than_the_memory_are_two_first_throws():
    """Without a window the count only ever climbs, so a companion left
    running all day comes for the mouse over two throws an hour apart."""
    temper = hoop.Temper()
    temper.thrown(1000.0)
    late = 1000.0 + hoop.THROW_MEMORY + 1.0
    assert temper.thrown(late) == 1, "an old throw was still being counted"
    assert not temper.furious(late)


def test_a_scored_basket_wipes_the_anger_and_a_miss_does_not():
    """Playing along is the way out and the only way out. If a miss also
    settled it, the basket would be a way of working the anger off by
    throwing at nothing, and the retaliation would never arrive."""
    game = hoop.HoopGame(SPRITE, RIM)
    game.thrown(1000.0)
    game.thrown(1001.0)
    assert game.temper.furious(1001.0)

    game.hoop = hoop.Hoop(1000.0, 400.0, RIM, 1001.0)
    # A flight that goes nowhere near it.
    assert not game.landed((100, 100), (160, 100), 1002.0)
    game.missed()
    assert game.temper.furious(1002.0), "a miss paid the debt off"
    assert game.misses == 1

    # And one that goes through it.
    assert game.landed((972 - 28, 400 - 28), (972 + 28, 400 - 28), 1002.0)
    assert game.score == 1
    assert not game.temper.furious(1002.0), "scoring did not clear the anger"


# ── where the basket goes ──

def test_the_basket_never_appears_on_top_of_the_character():
    """A basket the character could walk to is not a game, and one that lands
    under its feet reads as the sprite having spawned a bug.

    The floor is written out here rather than read off HOOP_CLEARANCE_SPRITES.
    Measured against the module's own constant this test says nothing at all:
    set the constant to zero and the assertion becomes `gap >= 0`, the defect
    and the instrument move together, and it passes. Three sprites is the
    independent claim — closer than that and the character walks over instead
    of being thrown.
    """
    floor = 3 * SPRITE
    assert hoop.HOOP_CLEARANCE_SPRITES * SPRITE >= floor, \
        "the clearance no longer puts the basket out of walking reach"
    here = (1000.0, 600.0)
    centre = (here[0] + SPRITE / 2, here[1] + SPRITE / 2)
    for seed in range(200):
        basket = hoop.place_hoop(here, SCREENS, SPRITE, RIM, 0.0,
                                 random.Random(seed))
        assert basket is not None
        gap = ((basket.x - centre[0]) ** 2 + (basket.y - centre[1]) ** 2) ** 0.5
        assert gap >= floor, f"seed {seed}: basket {gap:.0f} px away"


def test_the_basket_is_never_half_off_the_screen():
    """Drawn across an edge it is half a basket, and one flat against an edge
    can only be scored by a throw that ends outside the display."""
    for seed in range(200):
        for here in ((20.0, 20.0), (2100.0, 1150.0), (2200.0, 30.0),
                     (4000.0, 1100.0)):
            basket = hoop.place_hoop(here, SCREENS, SPRITE, RIM, 0.0,
                                     random.Random(seed))
            assert basket is not None
            screen = [s for s in SCREENS if _inside(s, basket.x, basket.y)]
            assert len(screen) == 1, f"seed {seed} from {here}: on {len(screen)} screens"
            left, top, width, height = screen[0]
            assert basket.x - RIM / 2 - SPRITE >= left
            assert basket.x + RIM / 2 + SPRITE <= left + width
            assert basket.y - RIM / 2 - SPRITE >= top
            assert basket.y + RIM / 2 + SPRITE <= top + height


def test_the_basket_lands_on_a_monitor_and_never_in_the_gap_between_two():
    """The union of these two screens contains rows and columns that belong to
    no display — they are 1234 and 1200 pixels tall and 1 px apart — and a
    basket drawn in one is invisible while looking perfectly right to the code.

    The character standing in one of those regions is the case that has to
    work: it has no screen of its own, and it still has to be offered a game.
    """
    # Where the character's own centre is, which is what decides the screen.
    in_the_gap = [(2194.5, 500.0), (3000.0, 1215.0)]
    assert not any(_inside(s, x, y) for s in SCREENS for x, y in in_the_gap), \
        "the probe is aiming at points that are on a screen after all"
    for seed in range(120):
        for cx, cy in in_the_gap:
            here = (cx - SPRITE / 2, cy - SPRITE / 2)
            basket = hoop.place_hoop(here, SCREENS, SPRITE, RIM, 0.0,
                                     random.Random(seed))
            assert basket is not None
            on = [s for s in SCREENS if _inside(s, basket.x, basket.y)]
            assert len(on) == 1, \
                f"seed {seed} from ({cx}, {cy}): basket at {basket.centre} is on {on}"


def test_no_drawing_means_no_basket():
    """The opening is buddy_sprites' number and is never repeated here. Until
    the art lands there is nothing to draw, and a hit area with no drawing in
    it is an invisible target — worse than no game."""
    game = hoop.HoopGame(SPRITE, rim=None)
    assert game.offer(1000.0, hoop.HOOP_AFTER + 1, (500.0, 500.0), SCREENS) is None
    assert not game.live(1000.0)
    assert hoop.place_hoop((500.0, 500.0), SCREENS, SPRITE, 0, 0.0) is None


def test_the_opening_is_read_from_the_art_in_the_pixels_everything_else_uses():
    """buddy_sprites.HOOP_RIM is a box in the art's own source pixels and every
    position here is in screen pixels. Taken raw it is half the width it should
    be, which does not look like a bug — it looks like a basket that is simply
    hard to hit — so the conversion is measured rather than assumed."""
    import buddy_sprites

    box = buddy_sprites.HOOP_RIM
    assert len(box) == 4, f"HOOP_RIM is no longer a box: {box!r}"
    width = hoop.rim_width()
    assert width == box[2] * buddy_sprites.SCALE, (width, box, buddy_sprites.SCALE)
    assert width > 0

    class NoHoopYet:
        SCALE = 2

    assert hoop.rim_width(NoHoopYet) is None, "invented an opening out of nothing"


def test_the_hit_area_follows_the_drawing_it_was_given():
    """The generosity is applied to the art's number rather than to a copy of
    it. A hit radius that ignores the rim it was handed is the same defect as
    hard-coding the rim here."""
    narrow = hoop.Hoop(0.0, 0.0, 20.0, 0.0).hit_radius(SPRITE)
    wide = hoop.Hoop(0.0, 0.0, 200.0, 0.0).hit_radius(SPRITE)
    assert wide - narrow == 90.0, (narrow, wide)
    # Generous, and provably so: the whole width that scores is the drawing
    # plus one sprite.
    assert narrow * 2 == 20.0 + SPRITE


# ── scoring ──

def test_a_throw_that_crosses_the_rim_between_two_frames_still_scores():
    """The one this module exists for. buddy_actions integrates in steps of up
    to MAX_STEP = 0.05 s, and at THROW_MAX_SPEED that is 120 px in one step —
    more than two sprite widths. Asking only whether the sprite is inside the
    hit area on this frame misses every throw fast enough to be worth
    watching, which is exactly the throws somebody aiming at a basket makes.
    """
    basket = hoop.Hoop(1000.0, 400.0, RIM, 0.0)
    radius = basket.hit_radius(SPRITE)
    start = (940.0 - SPRITE / 2, 400.0 - SPRITE / 2)
    end = (1060.0 - SPRITE / 2, 400.0 - SPRITE / 2)

    # Neither end of the step is in the hit area: a test written against the
    # sprite's position on a frame answers no to both of these.
    for corner in (start, end):
        centre = (corner[0] + SPRITE / 2, corner[1] + SPRITE / 2)
        away = ((centre[0] - basket.x) ** 2 + (centre[1] - basket.y) ** 2) ** 0.5
        assert away > radius, "the step under test does not actually skip the rim"

    assert basket.crossed(start, end, SPRITE), "a 120 px step tunnelled through"


def test_a_throw_that_goes_nowhere_near_does_not_score():
    """The segment test has to stay a test. Measured to the infinite line
    instead of the segment, a throw across the other side of the screen scores
    every basket that happens to be on its heading."""
    basket = hoop.Hoop(1000.0, 400.0, RIM, 0.0)
    assert not basket.crossed((100.0, 372.0), (300.0, 372.0), SPRITE)
    assert not basket.crossed((1500.0, 372.0), (1900.0, 372.0), SPRITE)
    assert not basket.crossed((972.0, 0.0), (972.0, 100.0), SPRITE)


def test_a_basket_that_has_been_scored_cannot_be_scored_again():
    """It has been used and it comes down. Left up, one flight scores it on
    every frame it is still inside the hit area, and a single throw runs the
    score into double figures."""
    game = hoop.HoopGame(SPRITE, RIM)
    game.hoop = hoop.Hoop(1000.0, 400.0, RIM, 100.0)
    through = ((940.0 - 28, 372.0), (1060.0 - 28, 372.0))
    assert game.landed(*through, 101.0)
    assert not game.landed(*through, 101.0)
    assert game.score == 1


# ── the offer, and what it holds back ──

def test_the_basket_is_offered_before_the_guaranteed_getaway():
    """The offer only exists if it arrives inside the window the companion
    already has. DRAG_PATIENCE is when it starts complaining and
    DRAG_TUG_ALWAYS is when the getaway fires with no cooldown and no
    forgiveness; a basket outside that pair is either indistinguishable from
    the complaint or arrives after the retaliation it was meant to replace."""
    patience = _companion_constant("DRAG_PATIENCE")
    always = _companion_constant("DRAG_TUG_ALWAYS")
    assert patience < hoop.HOOP_AFTER < always, (patience, hoop.HOOP_AFTER, always)
    # And there is room left to actually take it up: a throw's whole flight is
    # under two seconds at this gravity.
    assert always - hoop.HOOP_AFTER >= 2.0


def test_a_short_drag_is_offered_nothing():
    """Putting it down is not playing with it. A basket that appears every
    time the character is moved is a basket nobody asked for."""
    game = hoop.HoopGame(SPRITE, RIM)
    assert game.offer(1000.0, 0.5, (500.0, 500.0), SCREENS) is None
    assert game.offer(1000.0, hoop.HOOP_AFTER - 0.1, (500.0, 500.0), SCREENS) is None
    assert not game.live(1000.0)


def test_only_one_basket_goes_up_per_hold():
    """`offer` runs on the frame path. Answering with a fresh basket every
    time would move the target thirty times a second and hand the companion a
    new sentence to say on each of them."""
    game = hoop.HoopGame(SPRITE, RIM)
    first = game.offer(1000.0, hoop.HOOP_AFTER, (500.0, 500.0), SCREENS)
    assert first is not None
    for frame in range(1, 30):
        assert game.offer(1000.0 + frame * 0.033, hoop.HOOP_AFTER + frame * 0.033,
                          (500.0, 500.0), SCREENS) is None
    assert game.hoop is first


def test_the_getaway_waits_while_the_basket_is_up_and_resumes_when_it_goes():
    """The basket is an offer: throw me at that instead. Taking the mouse
    while it is still on screen withdraws the offer before anybody could
    accept it. And a basket that suspended the getaway forever would make
    holding the mouse down a way never to be retaliated against, which is the
    loophole the getaway exists to close."""
    game = hoop.HoopGame(SPRITE, RIM)
    game.thrown(1000.0)
    game.thrown(1001.0)
    assert game.should_chase(1001.0), "two throws and it is not even angry"

    assert game.offer(1002.0, hoop.HOOP_AFTER, (500.0, 500.0), SCREENS) is not None
    assert game.suspends_getaway(1002.0)
    assert not game.should_chase(1002.0), "took the mouse in the middle of the offer"

    almost = 1002.0 + hoop.HOOP_SECONDS - 0.1
    assert game.suspends_getaway(almost)
    assert not game.should_chase(almost)

    gone = 1002.0 + hoop.HOOP_SECONDS
    assert not game.suspends_getaway(gone), "the basket outstayed its own life"
    assert game.expired(gone)
    assert game.should_chase(gone), "ignoring the basket cost nothing"


def test_the_scoreboard_reads_the_same_facts_the_methods_do():
    """One read per frame, so the frame path cannot catch the basket already
    expired while the anger is still suspended by it."""
    game = hoop.HoopGame(SPRITE, RIM)
    blank = game.state(1000.0)
    assert blank.visible is False and blank.centre is None and blank.rim is None
    assert blank.expired is False and blank.score == 0 and blank.angry is False

    game.thrown(1000.0)
    game.thrown(1000.5)
    game.offer(1001.0, hoop.HOOP_AFTER, (500.0, 500.0), SCREENS)
    up = game.state(1001.0)
    assert up.visible is True and up.rim == RIM and up.angry is True
    assert up.centre == game.hoop.centre
    assert up.expired is False

    over = game.state(1001.0 + hoop.HOOP_SECONDS)
    assert over.visible is False and over.centre is None
    assert over.expired is True, "an ignored basket left no trace of itself"


# ── running at the pointer ──

def test_an_unknown_cursor_does_not_send_it_running_to_a_corner():
    """The measured failure. Under Wayland QCursor.pos() and xdotool read
    XWayland's shadow of the pointer, which stops following it over a native
    Wayland window — and a frozen reading cannot be told from a still one. So
    a reading that cannot be vouched for is refused, and the refusal costs the
    alignment and nothing else: the getaway still happens, from where the
    character stands, which is what shipped before this existed."""
    assert hoop.chase_target(None, 0.0, SPRITE, BOUNDS) is None
    assert hoop.chase_target((None, None), 0.0, SPRITE, BOUNDS) is None
    assert hoop.chase_target(("x", 4), 0.0, SPRITE, BOUNDS) is None
    assert hoop.chase_target((float("nan"), 4.0), 0.0, SPRITE, BOUNDS) is None
    # No age is "I cannot say how old this is", which is not an answer either.
    assert hoop.chase_target((900.0, 400.0), None, SPRITE, BOUNDS) is None
    # And a coordinate that is not on this desktop at all.
    assert hoop.chase_target((99999.0, 400.0), 0.0, SPRITE, BOUNDS) is None
    assert hoop.chase_target((-4000.0, 400.0), 0.0, SPRITE, BOUNDS) is None


def test_a_stale_reading_of_the_pointer_is_refused():
    """A position that was true half a second ago is a memory. The one reading
    this desktop can vouch for came in on a mouse event, and its age is the
    time since that event."""
    fresh = hoop.chase_target((900.0, 400.0), 0.0, SPRITE, BOUNDS)
    assert fresh is not None, "a reading from this instant was thrown away"
    assert hoop.chase_target((900.0, 400.0), hoop.CURSOR_STALE_AFTER - 0.01,
                             SPRITE, BOUNDS) is not None
    assert hoop.chase_target((900.0, 400.0), hoop.CURSOR_STALE_AFTER + 0.01,
                             SPRITE, BOUNDS) is None
    # Time that ran backwards is not a fresh reading, it is a broken clock.
    assert hoop.chase_target((900.0, 400.0), -1.0, SPRITE, BOUNDS) is None


def test_the_chase_starts_the_run_on_the_cursor_rather_than_beside_it():
    """This is the defect the leg exists to fix. The carry moves the pointer
    by the character's own per-frame delta and never by an absolute position,
    so the pointer arrives displaced by exactly the gap between the two when
    the run began. Landing the sprite's centre on the cursor makes that gap
    zero."""
    target = hoop.chase_target((900.0, 400.0), 0.0, SPRITE, BOUNDS)
    assert target == (900.0 - SPRITE / 2, 400.0 - SPRITE / 2), target
    # Near an edge the corner is clamped into the walking area, so the centre
    # misses by up to half a sprite and never by more.
    corner = hoop.chase_target((10.0, 10.0), 0.0, SPRITE, BOUNDS)
    assert corner == (BOUNDS[0], BOUNDS[1]), corner
    off = ((corner[0] + SPRITE / 2 - 10.0) ** 2
           + (corner[1] + SPRITE / 2 - 10.0) ** 2) ** 0.5
    assert off <= SPRITE, off


def test_a_pointer_in_the_inset_at_the_edge_of_a_screen_still_counts():
    """The bounds are already inset by 8 px and by a sprite, and a pointer
    resting in that inset is plainly on the desktop. Judging the reading
    against the walking area instead of the visible one refuses the corner of
    every screen."""
    assert hoop.chase_target((0.0, 0.0), 0.0, SPRITE, BOUNDS) is not None
    assert hoop.chase_target((4114.0, 1233.0), 0.0, SPRITE, BOUNDS) is not None
