"""The target, the record, the combo and the rally of catches.

Each test here is one way the game goes wrong. It scores the fast throws as
misses, because the flight is integrated in steps of up to MAX_STEP and a hard
throw is on one side of the rings on one frame and past them on the next. It
pays for grazing the outside, or pays the same for the edge as for the middle,
which teaches the player not to aim. It draws the target half off a screen, on
top of the character, on top of the basket, or in one of the regions of the
union of two monitors that belongs to no display. It announces a record for a
throw that only equalled the last one. It counts a rally the player got by
scooping the character off the floor. And it lets buddy_hoop's fury fire in
the middle of a rally, which is the game dying on the third throw.

Time is an argument throughout, so none of this sleeps, and nothing here
writes a file: the record is state the companion persists, and this module
only hands it over as a dict.
"""
import ast
import math
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import buddy_actions
import buddy_hoop
import buddy_target as target

# The sprite as the companion builds it: buddy_sprites.GRID 28 at SCALE 2.
SPRITE = 56

# MEASURED on the desktop this was written for, and quoted in buddy_actions:
# KWin and Qt both report HDMI-A-1 at (0, 0, 2194, 1234) and eDP-1 at
# (2195, 0, 1920, 1200). The two heights differ, which is what puts regions
# inside the union of the pair that belong to no monitor.
LEFT_SCREEN = (0, 0, 2194, 1234)
RIGHT_SCREEN = (2195, 0, 1920, 1200)
SCREENS = [LEFT_SCREEN, RIGHT_SCREEN]
SCREEN_H = 1234.0

# The companion's own bounds for that desktop: the union, inset by 8 px and by
# the sprite on the right and bottom, exactly as Companion.min_x .. max_y are.
BOUNDS = (8, 8, 4115 - SPRITE - 8, 1234 - SPRITE - 8)


class StubArt:
    """A stand-in for the drawing, which is another file's business.

    Radii in source pixels at a scale of its own, so a test can prove the
    conversion happens rather than assuming the one number the real art
    happens to publish today.
    """

    SCALE = 2
    TARGET_RINGS = (8, 16, 24)


RINGS = target.target_rings(StubArt)          # 16, 32, 48 screen px
RADIUS = RINGS[-1].radius


def _inside(rect, x, y):
    left, top, width, height = rect
    return left <= x < left + width and top <= y < top + height


def _corner(x, y):
    """A top-left corner whose sprite is centred on (x, y)."""
    return (x - SPRITE / 2.0, y - SPRITE / 2.0)


def _game(rings=RINGS):
    return target.ThrowGame(SPRITE, rings, screen_px=SCREEN_H)


# ── scoring ────────────────────────────────────────────────────────────────

def test_a_throw_that_crosses_the_face_between_two_frames_still_scores():
    """The one this module exists for. buddy_actions integrates in steps of up
    to MAX_STEP = 0.05 s, and at THROW_MAX_SPEED that is 120 px in one step —
    more than two sprite widths and wider than the whole face. Asking only
    whether the sprite is on the target on this frame misses every throw fast
    enough to be worth aiming, which is exactly the throws somebody aiming
    makes."""
    face = target.Target(1000.0, 400.0, RINGS, 0.0)
    start = _corner(1000.0 - 60.0, 400.0)
    end = _corner(1000.0 + 60.0, 400.0)

    # Neither end of the step is on the target at all: a test written against
    # the sprite's position on a frame answers no to both of these.
    for corner in (start, end):
        centre = (corner[0] + SPRITE / 2.0, corner[1] + SPRITE / 2.0)
        away = math.hypot(centre[0] - face.x, centre[1] - face.y)
        assert away > RADIUS, "the step under test does not actually skip the face"
    assert end[0] - start[0] <= buddy_actions.THROW_MAX_SPEED * buddy_actions.MAX_STEP

    hit = face.score(start, end, SPRITE)
    assert hit is not None, "a 120 px step tunnelled straight through the target"
    assert hit.ring == 1, hit


def test_a_throw_that_goes_nowhere_near_does_not_score():
    """The segment test has to stay a test. Measured to the infinite line
    instead of the segment, a throw across the other side of the screen scores
    every target that happens to be on its heading."""
    face = target.Target(1000.0, 400.0, RINGS, 0.0)
    assert face.score(_corner(100.0, 400.0), _corner(300.0, 400.0), SPRITE) is None
    assert face.score(_corner(1700.0, 400.0), _corner(1900.0, 400.0), SPRITE) is None
    assert face.score(_corner(1000.0, 0.0), _corner(1000.0, 100.0), SPRITE) is None


def test_the_middle_is_worth_more_than_the_edge_and_a_graze_pays_nothing():
    """Concentric rings that all pay the same are a circle, and a target that
    pays for passing near it teaches the player not to aim. The rings are the
    ones drawn: the middle of the character has to cross the ring it is being
    paid for, and a sprite whose body overlaps the face while its centre is
    outside has grazed it."""
    face = target.Target(1000.0, 400.0, RINGS, 0.0)

    def through(distance):
        return face.score(_corner(1000.0 - 200.0, 400.0 + distance),
                          _corner(1000.0 + 200.0, 400.0 + distance), SPRITE)

    middle = through(0.0)
    edge = through(RADIUS - 1.0)
    assert middle.ring == 1 and edge.ring == len(RINGS)
    assert middle.points > edge.points, (middle, edge)
    # And every step inward is worth strictly more than the step outside it.
    worth = [ring.points for ring in RINGS]
    assert worth == sorted(worth, reverse=True) and len(set(worth)) == len(worth), worth

    assert through(RADIUS + 1.0) is None, "grazing the outside paid"
    # The body of the sprite is well over the face there — 27 px of it inside
    # the outer ring — and it still pays nothing. That is the rule, and it is
    # the rule somebody watching can see being applied.
    assert RADIUS + 1.0 - SPRITE / 2.0 < RADIUS


def test_the_rings_are_read_from_the_art_and_never_recalculated_here():
    """The drawing declares its geometry in its own source pixels and every
    position in the module is in screen pixels. Taken raw the rings are half
    the size they should be, which does not look like a bug — it looks like a
    target that is oddly hard to hit — so the conversion is measured."""
    rings = target.target_rings(StubArt)
    assert [r.radius for r in rings] == [r * StubArt.SCALE
                                         for r in StubArt.TARGET_RINGS]

    class Bigger:
        SCALE = 3
        TARGET_RINGS = StubArt.TARGET_RINGS

    assert [r.radius for r in target.target_rings(Bigger)] == \
        [r * 3 for r in StubArt.TARGET_RINGS], "the art's scale was ignored"

    class NoTargetYet:
        SCALE = 2

    assert target.target_rings(NoTargetYet) is None, \
        "invented a target out of nothing"

    # And against the art as it actually is today, whichever side of the
    # drawing landing this test runs on.
    import buddy_sprites

    declared = None
    for name in target.ART_RINGS:
        declared = getattr(buddy_sprites, name, None)
        if declared is not None:
            break
    live = target.target_rings()
    if declared is None:
        assert live is None, "rings out of an art that declares none"
    else:
        assert live is not None and live[-1].radius > 0
        assert live[-1].radius == max(
            float(r[0] if isinstance(r, (tuple, list)) else r)
            for r in declared) * buddy_sprites.SCALE


def test_the_middle_of_the_rings_is_read_from_the_art_and_not_from_the_canvas():
    """buddy_sprites hangs the disc from a hook, so the rings are not centred
    in the image: six rows above them and two below. A companion that paints
    the drawing centred on the point a hit is measured against puts the
    bullseye several pixels off what it was aimed at, which reads as bad luck
    rather than as a bug — and the offset has to arrive already converted, or
    it is the ring conversion's mistake made twice."""
    class Hooked:
        SCALE = 2
        TARGET_CENTRE = (32, 40)

    assert target.target_centre(Hooked) == (64.0, 80.0)

    class Bigger(Hooked):
        SCALE = 3

    assert target.target_centre(Bigger) == (96.0, 120.0), "the scale was ignored"

    class NoTargetYet:
        SCALE = 2

    assert target.target_centre(NoTargetYet) is None

    import buddy_sprites

    spot = getattr(buddy_sprites, target.ART_CENTRE, None)
    live = target.target_centre()
    if spot is None:
        assert live is None, "a centre out of an art that declares none"
    else:
        assert live == (spot[0] * buddy_sprites.SCALE,
                        spot[1] * buddy_sprites.SCALE)
        # And it is genuinely not the middle of the canvas, which is the whole
        # reason this is read rather than derived from the image.
        assert live != (buddy_sprites.TARGET_W * buddy_sprites.SCALE / 2,
                        buddy_sprites.TARGET_H * buddy_sprites.SCALE / 2)


def test_no_drawing_means_no_target():
    """The rings are the art's numbers and are never repeated here. Until the
    drawing lands there is nothing to aim at, and a scoring area with nothing
    drawn in it is an invisible target — worse than no game."""
    game = target.ThrowGame(SPRITE, rings=None)
    game.released(1000.0, (500.0, 500.0), (900.0, -900.0))
    assert game.offer(1000.0, (500.0, 500.0), SCREENS) is None
    assert not game.live(1000.0)
    assert target.place_target((500.0, 500.0), SCREENS, SPRITE, (), 0.0) is None


# ── where the target goes ──────────────────────────────────────────────────

def test_the_target_never_appears_on_top_of_the_character():
    """A target the character could walk to is not a game, and one that lands
    under its feet reads as the sprite having spawned a bug.

    The floor is written out here rather than read off the module's own
    clearance. Measured against that constant this test says nothing: set it
    to zero and the assertion becomes `gap >= 0`, the defect and the
    instrument move together, and it passes. Three sprites is the independent
    claim — closer than that and walking over beats throwing.
    """
    floor = 3 * SPRITE
    assert target.TARGET_CLEARANCE_SPRITES * SPRITE >= floor, \
        "the clearance no longer puts the target out of walking reach"
    here = (1000.0, 600.0)
    centre = (here[0] + SPRITE / 2.0, here[1] + SPRITE / 2.0)
    for seed in range(200):
        face = target.place_target(here, SCREENS, SPRITE, RINGS, 0.0,
                                   random.Random(seed))
        assert face is not None
        gap = math.hypot(face.x - centre[0], face.y - centre[1])
        assert gap >= floor, f"seed {seed}: target {gap:.0f} px away"


def test_the_target_is_never_half_off_the_screen():
    """Drawn across an edge it is half a target, and one flat against an edge
    can only be scored by a throw that ends outside the display."""
    for seed in range(200):
        for here in ((20.0, 20.0), (2100.0, 1150.0), (2200.0, 30.0),
                     (4000.0, 1100.0)):
            face = target.place_target(here, SCREENS, SPRITE, RINGS, 0.0,
                                       random.Random(seed))
            assert face is not None
            screen = [s for s in SCREENS if _inside(s, face.x, face.y)]
            assert len(screen) == 1, f"seed {seed} from {here}: {len(screen)} screens"
            left, top, width, height = screen[0]
            assert face.x - RADIUS - SPRITE >= left
            assert face.x + RADIUS + SPRITE <= left + width
            assert face.y - RADIUS - SPRITE >= top
            assert face.y + RADIUS + SPRITE <= top + height


def test_the_target_lands_on_a_monitor_and_never_in_the_gap_between_two():
    """The union of these two screens contains rows and columns that belong to
    no display — they are 1234 and 1200 pixels tall and 1 px apart — and a
    target drawn in one is invisible while looking perfectly right to the code.

    The character standing in one of those regions is the case that has to
    work: it has no screen of its own, and it still has to be offered a game.
    """
    in_the_gap = [(2194.5, 500.0), (3000.0, 1215.0)]
    assert not any(_inside(s, x, y) for s in SCREENS for x, y in in_the_gap), \
        "the probe is aiming at points that are on a screen after all"
    for seed in range(120):
        for cx, cy in in_the_gap:
            here = _corner(cx, cy)
            face = target.place_target(here, SCREENS, SPRITE, RINGS, 0.0,
                                       random.Random(seed))
            assert face is not None
            on = [s for s in SCREENS if _inside(s, face.x, face.y)]
            assert len(on) == 1, \
                f"seed {seed} from ({cx}, {cy}): target at {face.centre} is on {on}"
            # And on the display the character is nearest to, worked out here
            # rather than asked of the module. "One screen" alone is a weak
            # claim on this desktop: the region belonging to no monitor is a
            # 1 px strip and a 34 px band, so a placement over the whole union
            # lands outside a screen once in a few hundred throws and a test
            # that only checks that passes while being wrong.
            near = min(SCREENS, key=lambda s: (s[0] + s[2] / 2 - cx) ** 2
                       + (s[1] + s[3] / 2 - cy) ** 2)
            assert on[0] == near, \
                f"seed {seed} from ({cx}, {cy}): target on {on[0]}, not {near}"


def test_the_target_is_not_drawn_on_top_of_the_basket_it_shares_the_screen_with():
    """The two games are on screen together on purpose, so the placement has
    to know about the other one. Overlapping drawings are not a scoring bug —
    they are a picture nobody can read, and the player cannot tell which of
    the two a throw was aimed at."""
    here = (400.0, 400.0)
    basket = (1400.0, 600.0, buddy_hoop.rim_width(StubArtHoop()) or 40.0)
    for seed in range(200):
        face = target.place_target(here, SCREENS, SPRITE, RINGS, 0.0,
                                   random.Random(seed), avoid=[basket])
        assert face is not None
        gap = math.hypot(face.x - basket[0], face.y - basket[1])
        assert gap >= RADIUS + basket[2] + SPRITE, \
            f"seed {seed}: target {gap:.0f} px from the basket"


class StubArtHoop:
    """A basket width for the placement test, in the art's own units."""

    SCALE = 2
    HOOP_RIM = (0, 0, 20, 10)


# ── the record ─────────────────────────────────────────────────────────────

def test_the_record_falls_only_to_a_longer_throw_and_never_to_a_tie():
    """A record announced on every equal throw is not a record. On a desktop
    where the character keeps landing in the same corner, most throws equal
    the last one, and the character would congratulate itself for all of
    them."""
    record = target.Record()
    assert record.log(500.0) is True and record.best == 500.0
    assert record.log(500.0) is False, "a tie was announced as a record"
    assert record.log(499.9) is False
    assert record.best == 500.0
    assert record.log(500.1) is True and record.best == 500.1
    # And nothing that is not a distance moves it.
    for junk in (None, "far", float("nan"), float("inf"), -1.0):
        assert record.log(junk) is False, junk
    assert record.best == 500.1


def test_the_record_survives_a_restart_without_this_module_touching_a_file():
    """The longest throw has to outlive the process or it is not a record, and
    it still must not be written from here: a module that opens files cannot
    be tested without a directory, and the operator's own cache is the
    directory it would reach for. The import list is the guard — one `import
    json` beside an `open()` is how that starts."""
    record = target.Record()
    record.log(1234.0)
    again = target.Record.from_dict(record.to_dict())
    assert again.best == 1234.0
    assert again.log(1234.0) is False, "the record came back as beatable"
    # Junk on disk is a record of zero, not an exception on startup.
    assert target.Record.from_dict({}).best == 0.0
    assert target.Record.from_dict(None).best == 0.0
    assert target.Record.from_dict({"best_px": "far"}).best == 0.0

    allowed = {"__future__", "math", "random", "collections",
               "buddy_actions", "buddy_hoop", "buddy_sprites"}
    source = (REPO / "scripts" / "buddy_target.py").read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= allowed, f"buddy_target grew an import: {imported - allowed}"


def test_the_distance_is_the_throw_and_not_the_path_it_took():
    """Measured from where it was let go to where it came to rest. Summing the
    steps instead would pay for bounces and for a body skidding along the
    floor after the throw was over, and the longest throw would be the one
    that rolled furthest."""
    game = _game()
    game.released(1000.0, (100.0, 100.0), (600.0, -600.0))
    throw = game.settled(1002.0, (400.0, 500.0))
    assert throw.distance == math.hypot(300.0, 400.0) == 500.0
    assert throw.record is True and throw.best == 500.0
    assert throw.force == target.FORCE_THROW

    # A release that was a placement is not a throw and cannot set a record.
    game.released(1003.0, (400.0, 500.0), (10.0, 10.0))
    quiet = game.settled(1004.0, (4000.0, 900.0))
    assert quiet.distance == 0.0 and quiet.record is False
    assert quiet.best == 500.0


# ── how hard it was thrown ─────────────────────────────────────────────────

def test_the_force_bands_come_from_the_physics_and_not_from_a_literal():
    """Every edge is a fact about buddy_actions' own constants. Frozen as a
    number here, they keep answering for a gravity or a step size that has
    since changed, and the symptom is a character that reacts to a hard throw
    as if it were a lob."""
    edges = target.force_edges(SPRITE, SCREEN_H)
    assert edges == (math.sqrt(2 * buddy_actions.GRAVITY * SPRITE),
                     SPRITE / buddy_actions.MAX_STEP,
                     math.sqrt(2 * buddy_actions.GRAVITY * SCREEN_H)), edges

    # The bottom edge means what its comment says, checked against the physics
    # rather than against the same algebra: thrown straight up at it, the
    # character rises about its own height. About, and not exactly, because
    # AIR_DRAG takes a few per cent out of the climb.
    x, y = 500.0, 800.0
    vx, vy = 0.0, -edges[0]
    apex = y
    for _ in range(400):
        step = buddy_actions.integrate((x, y), (vx, vy), 0.005, BOUNDS)
        x, y, vx, vy = step.x, step.y, step.vx, step.vy
        apex = min(apex, y)
        if vy > 0:
            break
    rise = 800.0 - apex
    assert 0.75 * SPRITE <= rise <= 1.05 * SPRITE, rise

    # And the middle edge is the speed at which one integration step moves the
    # character its own width, which is what makes a hit a segment.
    assert edges[1] * buddy_actions.MAX_STEP == SPRITE


def test_every_force_band_can_actually_be_reached_by_a_throw():
    """A band whose edge is outside the speeds throw_velocity can produce is a
    reaction the companion has and never uses. Both ends are fixed:
    THROW_MIN_SPEED is where a release stops being a placement and
    THROW_MAX_SPEED is the scaling cap."""
    lo, hi = buddy_actions.THROW_MIN_SPEED, buddy_actions.THROW_MAX_SPEED
    edges = target.force_edges(SPRITE, SCREEN_H)
    assert lo < edges[0] < edges[1] < edges[2] < hi, edges

    seen = [target.force_band(speed, SPRITE, SCREEN_H) for speed in
            (lo, (edges[0] + edges[1]) / 2, (edges[1] + edges[2]) / 2, hi)]
    assert seen == list(target.FORCES), seen
    # Below the floor there is no band at all, because nothing was thrown.
    assert target.force_band(lo - 1.0, SPRITE, SCREEN_H) is None
    assert target.throw_force((0.0, 0.0), SPRITE, SCREEN_H) is None
    assert target.throw_force(None, SPRITE, SCREEN_H) is None
    assert target.throw_force((float("nan"), 1.0), SPRITE, SCREEN_H) is None


# ── the combo of hits ──────────────────────────────────────────────────────

def test_the_combo_breaks_on_a_miss_and_on_nothing_else():
    """A counter anything can reset is one the player cannot predict. What
    breaks a run of hits is a throw that missed a target that was up; a target
    nobody threw at, a catch, and a throw taken with nothing on screen are not
    failures and must not read as one."""
    game = _game()
    game.target = target.Target(1000.0, 400.0, RINGS, 1000.0)
    across = (_corner(800.0, 400.0), _corner(1200.0, 400.0))
    assert game.landed(across[0], across[1], 1000.0).combo == 1
    game.target = target.Target(1000.0, 400.0, RINGS, 1001.0)
    assert game.landed(across[0], across[1], 1001.0).combo == 2

    # A throw with nothing on screen: there was nothing to miss.
    game.released(1002.0, (100.0, 100.0), (900.0, -900.0))
    game.settled(1003.0, (900.0, 700.0))
    assert game.state(1003.0).combo == 2, "a throw at nothing broke the run"

    # A target that expired with nobody throwing at it: an offer, not a debt.
    game.target = target.Target(1000.0, 400.0, RINGS, 1003.0)
    gone = 1003.0 + target.TARGET_SECONDS + 1.0
    assert game.expired(gone) and not game.live(gone)
    assert game.state(gone).combo == 2, "an ignored target broke the run"

    # Being caught in mid-air is the other game's business.
    game.released(gone, (100.0, 100.0), (1500.0, -900.0))
    assert game.caught(gone + 0.2, 900.0) is not None
    assert game.state(gone + 0.2).combo == 2, "a catch broke the run of hits"

    # And a throw that came to rest with a target still up is a miss.
    game.target = target.Target(1000.0, 400.0, RINGS, gone)
    game.released(gone + 0.3, (100.0, 100.0), (900.0, -900.0))
    game.settled(gone + 1.0, (200.0, 700.0))
    assert game.state(gone + 1.0).combo == 0, "a miss did not break the run"
    assert game.misses == 1


def test_a_run_of_hits_expires_with_the_same_memory_the_temper_uses():
    """Without a window the count only ever climbs, so a companion left
    running all day announces a five-hit run made of five throws an hour
    apart. The window is buddy_hoop's, so forgiving and congratulating happen
    on the same clock."""
    assert target.COMBO_MEMORY == buddy_hoop.THROW_MEMORY
    combo = target.Combo()
    assert combo.hit(1000.0) == 1
    assert combo.hit(1000.0 + target.COMBO_MEMORY - 1.0) == 2
    late = 1000.0 + 2 * target.COMBO_MEMORY
    assert combo.hit(late) == 1, "an expired run was still being counted"
    assert combo.best == 2


# ── the rally of catches ───────────────────────────────────────────────────

def test_a_catch_in_the_air_counts_and_a_scoop_off_the_floor_does_not():
    """Catching it mid-flight is timing; picking it up once it is hopping
    along the floor is not, and paying for that makes the whole rally free.
    The line is a speed and not a number of bounces: the same third bounce is
    a body still hundreds of pixels up after a throw at the ceiling and a body
    vibrating on the floor after a lob."""
    lively = target.lift_speed(SPRITE)

    game = _game()
    game.released(1000.0, (500.0, 500.0), (1200.0, -1200.0))
    caught = game.caught(1000.4, 1400.0)
    assert caught is not None and caught.run == 1

    # A bounce that left it able to lift itself its own height is still a
    # flight, and catching it there is still a catch.
    game.released(1000.6, (500.0, 500.0), (1200.0, -1200.0))
    game.bounced(lively * 1.5)
    again = game.caught(1001.4, 700.0)
    assert again is not None and again.run == 2

    # One that did not is the tail of the flight. The scoop pays nothing and
    # ends the rally that was standing.
    game.released(1001.6, (500.0, 500.0), (1200.0, -1200.0))
    game.bounced(lively * 0.5)
    assert game.caught(1002.4, 100.0) is None, "a scoop off the floor counted"
    assert game.state(1002.4).rally == 0, "the rally survived the scoop"


def test_the_rally_breaks_by_dropping_putting_down_and_holding_on():
    """Three ways to stop juggling, and each of them has to end the count or
    the count is not about juggling. Landing is dropping it. A release under
    THROW_MIN_SPEED is a placement, and without that rule a rally could be
    parked on the desktop indefinitely. And holding on past the point where
    the character itself asks to be put down is not a rally either."""
    # Dropped.
    game = _game()
    game.released(1000.0, (500.0, 500.0), (1200.0, -1200.0))
    assert game.caught(1000.4, 900.0).run == 1
    game.released(1000.6, (500.0, 500.0), (1200.0, -1200.0))
    game.settled(1002.0, (900.0, 700.0))
    assert game.state(1002.0).rally == 0, "letting it land kept the rally"

    # Put down.
    game = _game()
    game.released(1000.0, (500.0, 500.0), (1200.0, -1200.0))
    assert game.caught(1000.4, 900.0).run == 1
    assert game.released(1000.6, (500.0, 500.0), (5.0, 5.0)) is None
    assert game.state(1000.6).rally == 0, "putting it down kept the rally"

    # Held on to. The window is the companion's DRAG_PATIENCE, the moment the
    # character starts asking to be put down.
    game = _game()
    game.released(1000.0, (500.0, 500.0), (1200.0, -1200.0))
    assert game.caught(1000.4, 900.0).run == 1
    assert game.state(1000.4 + target.JUGGLE_HOLD - 0.1).rally == 1
    assert game.state(1000.4 + target.JUGGLE_HOLD + 0.1).rally == 0, \
        "holding on to it forever kept the rally alive"
    assert target.JUGGLE_HOLD == 3.5, "no longer the companion's DRAG_PATIENCE"


def test_the_rally_is_not_broken_by_the_other_game():
    """The two counters are separate on purpose and they must not reach into
    each other. A throw that scores on the way past is still a throw that can
    be caught, and a target nobody threw at has nothing to do with the hands
    holding the character."""
    game = _game()
    game.released(1000.0, (500.0, 500.0), (1200.0, -1200.0))
    assert game.caught(1000.4, 900.0).run == 1

    game.released(1000.6, (500.0, 500.0), (1200.0, -1200.0))
    game.target = target.Target(1000.0, 400.0, RINGS, 1000.6)
    hit = game.landed(_corner(800.0, 400.0), _corner(1200.0, 400.0), 1000.8)
    assert hit is not None and hit.combo == 1
    assert game.caught(1000.9, 900.0).run == 2, "a hit ended the rally"

    game.released(1001.0, (500.0, 500.0), (1200.0, -1200.0))
    game.target = target.Target(1000.0, 400.0, RINGS, 1001.0)
    gone = 1001.0 + target.TARGET_SECONDS + 1.0
    assert game.expired(gone)
    assert game.caught(gone, 900.0).run == 3, "an expired target ended the rally"


def test_a_hard_catch_and_a_gentle_one_are_told_apart():
    """A rally that pays the same for every catch is a rally everybody plays
    gently, which is a dead rally. Difficulty is the speed the body was doing
    when the hand closed on it — a hard throw caught at the top of its arc is
    barely moving, and catching it there is easy."""
    edges = target.force_edges(SPRITE, SCREEN_H)
    game = _game()

    game.released(1000.0, (500.0, 500.0), (1200.0, -1200.0))
    fast = game.caught(1000.2, edges[2] + 10.0)
    game.released(1000.4, (500.0, 500.0), (1200.0, -1200.0))
    gentle = game.caught(1000.6, edges[0] - 10.0)
    game.released(1000.8, (500.0, 500.0), (1200.0, -1200.0))
    drifting = game.caught(1001.0, 1.0)

    assert fast.force == target.FORCE_LAUNCH and gentle.force == target.FORCE_TOSS
    assert fast.points > gentle.points, (fast, gentle)
    # A body drifting slower than the character walks has no band at all, and
    # is worth the minimum rather than nothing: it was still a catch.
    assert drifting.force is None and drifting.points == gentle.points
    assert drifting.run == 3 and fast.points == len(target.FORCES)


# ── the two games and the temper ───────────────────────────────────────────

def test_the_game_holds_the_getaway_off_while_it_runs_and_never_forgives_it():
    """Juggling is by construction a lot of throws in a row, and buddy_hoop
    comes for the mouse on the second inside ninety seconds. Left to meet by
    accident, the fury fires on the third throw of every rally and the game
    dies there.

    Suspension is the answer and forgiveness is not: buddy_hoop says scoring a
    basket is the way out "and there is no other", so a rally that wiped the
    temper would quietly remove the retaliation the basket exists to buy off.
    """
    hoop = buddy_hoop.HoopGame(SPRITE, rim=40.0)
    hoop.thrown(1000.0)
    hoop.thrown(1001.0)
    assert hoop.should_chase(1001.5), "the scenario is not actually a furious one"

    game = _game()
    game.released(1001.0, (500.0, 500.0), (1200.0, -1200.0))
    assert game.caught(1001.4, 900.0).run == 1
    assert game.suspends_getaway(1001.5), "a rally did not hold the getaway off"
    # The seam the companion has to write, and the whole point of the method.
    assert not (hoop.should_chase(1001.5) and not game.suspends_getaway(1001.5))
    # Suspended, not paid off.
    assert hoop.temper.furious(1001.5), "the rally forgave the temper"

    # A target on screen holds it off the same way, and for the same reason.
    game.released(1001.6, (500.0, 500.0), (1200.0, -1200.0))
    game.settled(1002.0, (900.0, 700.0))
    assert game.state(1002.0).rally == 0
    assert game.offer(1002.0, (900.0, 700.0), SCREENS,
                      random.Random(1)) is not None
    assert game.suspends_getaway(1002.0)

    # And when the game is over the character is exactly as angry as it was.
    over = 1002.0 + target.TARGET_SECONDS + 1.0
    assert not game.suspends_getaway(over)
    assert hoop.should_chase(over), "the getaway never arrived"


def test_the_target_is_offered_by_a_throw_and_never_by_a_placement():
    """The target is what a throw earns. Offered on a release that was a
    placement, it appears because somebody moved the character out of the way,
    which is the companion doing things nobody asked for."""
    game = _game()
    game.released(1000.0, (500.0, 500.0), (5.0, 5.0))
    assert game.offer(1000.5, (500.0, 500.0), SCREENS, random.Random(1)) is None

    game.released(1001.0, (500.0, 500.0), (1200.0, -1200.0))
    game.settled(1002.0, (900.0, 700.0))
    face = game.offer(1002.0, (900.0, 700.0), SCREENS, random.Random(1))
    assert face is not None and game.live(1002.0)
    # And never a second one on top of the first.
    assert game.offer(1002.5, (900.0, 700.0), SCREENS, random.Random(2)) is None
    assert game.target is face


def test_a_target_that_has_been_hit_comes_down_and_cannot_be_hit_again():
    """It has been used. Left up, one flight scores it on every step it is
    still inside the rings, and a single throw runs the count to five."""
    game = _game()
    game.target = target.Target(1000.0, 400.0, RINGS, 1000.0)
    across = (_corner(800.0, 400.0), _corner(1200.0, 400.0))
    assert game.landed(across[0], across[1], 1000.0) is not None
    assert game.landed(across[0], across[1], 1000.0) is None
    assert game.hits == 1 and not game.live(1000.0)


def test_the_scoreboard_reads_the_same_facts_the_methods_do():
    """One read per frame, so the frame path cannot catch the target already
    expired while the getaway is still suspended by it."""
    game = _game()
    blank = game.state(1000.0)
    assert blank.visible is False and blank.centre is None
    assert blank.radius is None and blank.expired is False
    assert blank.hits == 0 and blank.misses == 0
    assert blank.combo == 0 and blank.rally == 0 and blank.record == 0.0

    game.released(1000.0, (100.0, 100.0), (1200.0, -1200.0))
    game.settled(1001.0, (900.0, 700.0))
    face = game.offer(1001.0, (900.0, 700.0), SCREENS, random.Random(3))
    up = game.state(1001.0)
    assert up.visible is True and up.centre == face.centre
    assert up.radius == face.radius and up.expired is False
    assert up.record == game.record.best > 0.0

    over = game.state(1001.0 + target.TARGET_SECONDS)
    assert over.visible is False and over.centre is None
    assert over.expired is True, "an ignored target left no trace of itself"
