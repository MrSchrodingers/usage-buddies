"""A target to throw the character at, and what throwing it is worth.

The same shape as buddy_hoop, buddy_focus and buddy_idle: no Qt, no timers, no
clock of its own. Time, geometry, the sprite size and the randomness all
arrive as arguments, and anything this cannot know is None rather than a
plausible number. The companion owns the frame clock, the window, the painting
and the words; this owns the arithmetic and the verdicts.

Four things, and they are four because each of them ends at a different
moment and is announced by a different sentence:

  target  concentric rings somewhere on one screen. A throw is scored against
          the rings the art draws, and the middle is worth more than the edge.
  record  the longest throw so far, in pixels, and whether this one beat it.
  combo   hits in a row, broken by a throw that missed a target that was up.
  juggle  catches in a row: thrown, caught in mid-air, thrown again. Broken by
          letting it land, by putting it down, and by holding on to it.

The coordinate convention is buddy_actions' and is the same throughout:
positions are the sprite's top-left corner, and screens are
(left, top, width, height), which is what Companion._screen_rects hands out.
The target's own position is the centre of its face, because that is what a
hit is measured against.

── the target and the basket are on screen together ────────────────────────

Deliberately, and this is the decision most likely to be revisited, so the
argument is here rather than in a commit message.

buddy_hoop's basket is an apology: it is offered during a drag that has gone
on for HOOP_AFTER = 6 s, it lasts HOOP_SECONDS = 12 s, and scoring it is the
one and only thing that clears the temper. The target is a toy: it is put up
by an ordinary throw and it is there to be thrown at again. Making either one
hide the other costs something real — the basket is rare and would be eaten by
the toy, and the toy would vanish exactly when somebody is playing with it —
so both are on screen, and place_target's `avoid` keeps the new one clear of
the old one so the two drawings never overlap.

What the target does NOT get is the basket's second power. Scoring a basket
forgives the temper in full; hitting the target does not, and neither does a
rally of catches. buddy_hoop says in as many words that playing along is the
way out "and there is no other", and a second forgiver would weaken the
retaliation without anybody deciding to. What the target and the rally do get
is suspension: while either is live the getaway waits, because retaliating in
the middle of a game the character is playing withdraws the offer. That is
bounded — the target by TARGET_SECONDS, the rally by the player's own hands,
since a rally that is not fed a catch every couple of seconds dies on its own.

The seam that has to be got right is one line in the companion:
should_chase becomes `hoop.should_chase(now) and not game.suspends_getaway(now)`.
Forget it and the fury fires in the middle of a rally, which is the game dying
on the third throw.

── where the record lives ──────────────────────────────────────────────────

A longest throw that resets at every login is not a record, so it has to
outlive the process. It is not written here: this module does no I/O, and the
one place the companion already owns for state of its own is
CACHE = $XDG_CACHE_HOME/usage-buddies (usage-buddy-companion.py line 63), so
`CACHE / "companion-records.json"` is the file and Record.to_dict /
Record.from_dict is what goes in it. Keeping the write out of here also keeps
the tests out of the operator's real cache: a test can round-trip the dict
without a path existing at all.
"""
from __future__ import annotations

import math
import random
from collections import namedtuple

import buddy_actions
import buddy_hoop

# The screen choice and the point-to-segment distance are buddy_hoop's, bound
# here rather than rewritten. The first is a decision and not a formula — a
# character standing in one of the regions of the union of two monitors that
# belongs to no display still has to be offered a game, and it gets the
# nearest real screen — and a decision answered twice is two answers that
# drift. They are private names over there; the coupling is deliberate and it
# fails loudly, at import, if either is renamed.
_screen_for = buddy_hoop._screen_for
_segment_distance = buddy_hoop._segment_distance


# ── how hard it was thrown ─────────────────────────────────────────────────

# The tallest screen on the desktop this was written for. MEASURED, and the
# same reading buddy_actions' GRAVITY was chosen against: KWin and Qt both
# report HDMI-A-1 at (0, 0, 2194, 1234) and eDP-1 at (2195, 0, 1920, 1200).
# It is a default and not a truth — the companion knows the screen the
# character is actually on and should pass it.
TALLEST_SCREEN_PX = 1234.0

# The bands, weakest first. The companion picks a reaction from the name and
# can compare two throws with FORCES.index, which is why this is an ordered
# tuple and not a set.
FORCE_TOSS = "toss"
FORCE_THROW = "throw"
FORCE_HURL = "hurl"
FORCE_LAUNCH = "launch"
FORCES = (FORCE_TOSS, FORCE_THROW, FORCE_HURL, FORCE_LAUNCH)


def lift_speed(sprite_px):
    """The speed at which the character can just lift itself its own height.

    v = sqrt(2 * GRAVITY * h) with h the sprite, which at the measured sprite
    (56 px) and buddy_actions.GRAVITY (1900) is 461 px/s. Two things are
    decided by it and they are the same question asked twice, which is why it
    is one function rather than two constants: below it a throw does not get
    the character off your hand, and below it a body that has bounced is
    hopping rather than flying.

    Derived, never written down as a number: GRAVITY was itself chosen from
    the arc it produces, and a literal here would keep the old answer the day
    that changes.
    """
    return math.sqrt(2.0 * buddy_actions.GRAVITY * float(sprite_px))


def force_edges(sprite_px, screen_px=TALLEST_SCREEN_PX):
    """The three speeds that separate the four bands, ascending.

    Every one of them is a fact about this physics rather than a taste:

      lift    sqrt(2 * GRAVITY * sprite) — 461 px/s at the measured sprite. It
              cannot raise itself its own height, which is what a throw that
              barely left the hand looks like.
      tunnel  sprite / MAX_STEP — 1120 px/s. buddy_actions integrates in steps
              of at most 0.05 s, so above this the body moves more than its
              own width between two frames: fast enough to pass through
              something without ever being drawn inside it, which is the whole
              reason a hit is a segment here and not a point.
      over    sqrt(2 * GRAVITY * screen) — 2165 px/s on the tallest screen
              measured. Thrown straight up it leaves the top of the display.

    Sorted rather than assumed in order: the three depend on the sprite and on
    the screen, and a caller with an unusual pair of those would otherwise get
    bands that overlap silently.
    """
    sprite = float(sprite_px)
    lift = lift_speed(sprite)
    tunnel = sprite / buddy_actions.MAX_STEP
    over = math.sqrt(2.0 * buddy_actions.GRAVITY * float(screen_px))
    return tuple(sorted((lift, tunnel, over)))


def force_band(speed, sprite_px, screen_px=TALLEST_SCREEN_PX):
    """Which of FORCES a speed is, or None when it is not a throw at all.

    None below buddy_actions.THROW_MIN_SPEED, which is the number that already
    means "this was a placement, not a throw" — throw_velocity returns (0, 0)
    there. The caller has no reaction to choose because nothing was thrown,
    and that is a different answer from "it was thrown gently".
    """
    try:
        value = float(speed)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value < buddy_actions.THROW_MIN_SPEED:
        return None
    edges = force_edges(sprite_px, screen_px)
    return FORCES[sum(1 for edge in edges if value >= edge)]


def throw_force(vel, sprite_px, screen_px=TALLEST_SCREEN_PX):
    """The band of a velocity pair, as throw_velocity hands it out, or None."""
    try:
        vx, vy = float(vel[0]), float(vel[1])
    except (TypeError, ValueError, IndexError, KeyError):
        return None
    if not (math.isfinite(vx) and math.isfinite(vy)):
        return None
    return force_band(math.hypot(vx, vy), sprite_px, screen_px)


# ── the rings, which are the art's and not this module's ───────────────────

Ring = namedtuple("Ring", "radius points")

# Where the geometry comes from, in the art's own source pixels, and what it
# is converted with. buddy_sprites.HOOP_RIM set the precedent: the drawing
# knows where the hole is, and the same numbers written again beside whatever
# decides that a throw scored are two truths that diverge the first time the
# drawing moves by a pixel.
#
# Two names accepted, in this order, and no more. The first is the contract;
# the second is the one synonym, because the drawing and this file were
# written in the same turn by different hands and a seam must not break on a
# choice of noun. Anything else, and there is no target — see target_rings.
ART_RINGS = ("TARGET_RINGS", "TARGET_RING_RADII")

# Where the rings are centred on the art's own canvas, in source pixels. It is
# not the middle of the image and must not be assumed to be: buddy_sprites
# hangs the disc from a hook, with six rows above it and two below, so placing
# the drawing by the middle of its rectangle puts the bullseye several pixels
# off whatever it was aimed at — which looks like bad luck rather than like a
# bug. target_centre() converts it once, here, for the same reason the radii
# are converted here.
ART_CENTRE = "TARGET_CENTRE"


def _radii(declared):
    """Source-pixel radii out of whatever shape the art published them in.

    Accepts a flat sequence of numbers, and a sequence whose entries begin
    with the radius — so an art that pairs each ring with its colour still
    reads. What it does not do is invent one: anything unreadable is dropped,
    and a declaration that leaves nothing behind is no target at all.
    """
    out = []
    for entry in declared or ():
        value = entry
        if isinstance(entry, (tuple, list)) and entry:
            value = entry[0]
        try:
            radius = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(radius) and radius > 0:
            out.append(radius)
    return sorted(set(out))


def _points(radii):
    """What each ring is worth, innermost first, for radii in that order.

    Derived rather than tabulated, because the number of rings belongs to the
    drawing and a table here would have to be edited the day the art gains
    one. A ring is worth what it is hard to hit: aim at the face at random and
    the chance of ending in a band is its share of the area, which for a ring
    at radius r inside one at R is proportional to R^2 - r^2. The outermost
    band is one point and every other is the ratio of the two areas, rounded.

    At the equally spaced radii a target is usually drawn with, that is 5, 2,
    1 for three rings — the middle is worth what it costs to hit.

    The last pass is not cosmetic. Rounding can tie two neighbours, and a
    bullseye worth exactly as much as the ring around it is the one thing this
    must never produce: it makes the drawing a lie.
    """
    areas = []
    inner = 0.0
    for radius in radii:
        areas.append(radius * radius - inner * inner)
        inner = radius
    if not areas:
        return []
    outer = areas[-1]
    points = [max(1, round(outer / area)) for area in areas]
    for i in range(len(points) - 2, -1, -1):
        points[i] = max(points[i], points[i + 1] + 1)
    return points


def target_rings(art=None):
    """The rings in screen pixels, innermost first, or None.

    This is the one place the art's source pixels become the pixels every
    position in this module is in, and it is here for the reason
    buddy_hoop.rim_width is there: getting it wrong is invisible. Rings taken
    raw are half the size they should be, which does not read as a bug — it
    reads as a target that is oddly hard to hit.

    None when the art declares no rings, which is not an error. There is
    simply no target to offer, the rest of the game works, and the drawing
    landing later turns it on with no change here. The import is inside the
    function so this module keeps its promise of importing nothing that can
    fail.
    """
    if art is None:
        try:
            import buddy_sprites as art
        except ImportError:
            return None
    declared = None
    for name in ART_RINGS:
        declared = getattr(art, name, None)
        if declared is not None:
            break
    if declared is None:
        return None
    try:
        scale = float(getattr(art, "SCALE", 1))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(scale) or scale <= 0:
        return None
    radii = [r * scale for r in _radii(declared)]
    if not radii:
        return None
    return tuple(Ring(r, p) for r, p in zip(radii, _points(radii)))


def target_centre(art=None):
    """Where the rings sit inside the drawing, in screen pixels, or None.

    (dx, dy) from the top-left of the image to the middle of the rings. The
    companion needs it to paint: Target.x and Target.y are the middle of the
    rings, because that is what a hit is measured against, and the image has
    to be drawn at (x - dx, y - dy) rather than centred on its own rectangle.

    It is here rather than at the seam for the reason the radii are: this is
    the one place the art's source pixels become screen pixels, and an offset
    converted twice is an offset that will one day be converted once.
    """
    if art is None:
        try:
            import buddy_sprites as art
        except ImportError:
            return None
    spot = getattr(art, ART_CENTRE, None)
    if spot is None:
        return None
    try:
        scale = float(getattr(art, "SCALE", 1))
        x, y = float(spot[0]) * scale, float(spot[1]) * scale
    except (TypeError, ValueError, IndexError, KeyError):
        return None
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    return (x, y)


# ── the target on the desktop ──────────────────────────────────────────────

# How long it stays up. The basket's 12 s is measured against a drag that is
# already in progress; this one starts with the character free, so the clock
# is the attempts it has to allow. An attempt at its very worst is a hold that
# reaches the companion's DRAG_PATIENCE (3.5 s, the point at which it starts
# complaining) plus a flight at the speed ceiling, which is 2 * v / GRAVITY =
# 2.5 s up and down again: six seconds. Three of those is 18 s, and at the
# pace somebody actually throws — a grab and a flick, under two seconds — it
# is nearer ten attempts.
TARGET_SECONDS = 20.0

# How far from the character it appears, centre to centre, in sprite widths.
# buddy_hoop's number and not one of this module's: how far away a thing has
# to be before walking to it stops being easier than throwing at it is a fact
# about the character's own speed, not about what is drawn there, and two
# answers to it would drift.
TARGET_CLEARANCE_SPRITES = buddy_hoop.HOOP_CLEARANCE_SPRITES

# How many places are tried before the clearance is given up on. Also
# buddy_hoop's, and with it the fallback: on a screen with no room for the
# clearance, the furthest of what was sampled is the best answer available,
# and refusing to place anything would silently remove the game on a small
# display rather than making it slightly too easy on one.
TARGET_TRIES = buddy_hoop.HOOP_TRIES


class Target:
    """Rings on the desktop: where the middle is, and when it appeared.

    `x` and `y` are the centre of the face rather than a corner, because the
    centre is what a hit is measured against.

    `rings` are Rings in screen pixels, innermost first, as target_rings
    hands them out. They are carried rather than known, for the same reason
    buddy_hoop.Hoop carries its rim: the drawing owns the geometry.
    """

    def __init__(self, x, y, rings, shown_at):
        self.x = float(x)
        self.y = float(y)
        self.rings = tuple(rings)
        self.shown_at = float(shown_at)

    @property
    def centre(self):
        return (self.x, self.y)

    @property
    def radius(self):
        """The outer edge, which is the whole of what can be scored."""
        return self.rings[-1].radius if self.rings else 0.0

    def expired(self, now, life=TARGET_SECONDS):
        return now - self.shown_at >= float(life)

    def closest(self, start, end, sprite_px):
        """How near the middle of the character got to the middle of the face.

        The travel is a segment and not its two endpoints, and that is the
        whole reason this exists. buddy_actions integrates in steps of up to
        MAX_STEP = 0.05 s, and at THROW_MAX_SPEED that is 120 px in one step —
        more than two sprite widths and wider than most of the face. Asking
        only whether the sprite is on the target on this frame misses every
        throw fast enough to be worth aiming, which is exactly the throws
        somebody aiming makes.

        `start` and `end` are top-left corners, the companion's convention;
        the centres are what travel.
        """
        half = float(sprite_px) / 2.0
        a = (float(start[0]) + half, float(start[1]) + half)
        b = (float(end[0]) + half, float(end[1]) + half)
        return _segment_distance(self.centre, a, b)

    def score(self, start, end, sprite_px):
        """What one step of a flight scored, or None for nothing.

        Measured to the centre of the sprite against the rings as drawn, with
        no slack added anywhere. buddy_hoop is generous by half a sprite and
        is right to be: its basket is a hole barely wider than the thing you
        throw into it (76 px against a 56 px sprite), and in-or-out has to
        forgive something. This target does not need it — the art's disc is
        112 px across at SCALE 2, so a centre on the outer ring is a character
        sitting squarely on the drawing, and the bullseye is 40 px across
        against a sprite of 56, which the character covers entirely from a
        centre inside it. Being generous here costs what buddy_sprites asks it
        not to cost: slack has to be applied to every ring, which moves each
        boundary outward and makes the bullseye a circle the size of the
        bullseye plus half a sprite — "a middle that cannot be missed is not a
        middle", in the art's own words, and grazing the outer edge would pay
        as well. Passing the middle of
        the character over the ring it is drawn on is the rule, and it is a
        rule somebody watching can see being applied.
        """
        if not self.rings:
            return None
        near = self.closest(start, end, sprite_px)
        for index, ring in enumerate(self.rings):
            if near <= ring.radius:
                return Hit(points=ring.points, ring=index + 1,
                           rings=len(self.rings), closest=near,
                           combo=0, best=0)
        return None


Hit = namedtuple("Hit", "points ring rings closest combo best")


def _avoid(spots):
    """(x, y, radius) triples out of what the caller wants kept clear."""
    out = []
    for spot in spots or ():
        try:
            x, y = float(spot[0]), float(spot[1])
            radius = float(spot[2]) if len(spot) > 2 else 0.0
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if math.isfinite(x) and math.isfinite(y) and math.isfinite(radius):
            out.append((x, y, radius))
    return out


def place_target(position, screens, sprite_px, rings, now, rng=random,
                 avoid=()):
    """Somewhere on one screen to put a target, or None.

    The constraints are buddy_hoop.place_hoop's, for the reasons written out
    there, and they are ways the placement is wrong rather than preferences:
    one screen and never the union of two, because the union contains regions
    that belong to no display; the screen the character is on, because the
    flight is ballistic and bounded and a target on the other monitor cannot
    be reached; clear of the edges by the face and a whole sprite, so it is
    wholly visible and can be reached from outside; and clear of the character
    itself, or it could be walked to.

    One constraint of its own: `avoid`, a sequence of (x, y) or (x, y, radius)
    the new target must not be drawn on top of. The companion passes the
    basket, because the two games share the screen on purpose.

    None when there is nothing to draw or no screen to draw it on.
    """
    rings = tuple(rings or ())
    if not rings:
        # No art, no target. A scoring area with nothing drawn in it is an
        # invisible target, which is worse than no game at all.
        return None
    sprite = float(sprite_px)
    radius = max(ring.radius for ring in rings)
    if not math.isfinite(radius) or radius <= 0:
        return None
    here = (float(position[0]) + sprite / 2.0,
            float(position[1]) + sprite / 2.0)
    screen = _screen_for(here, screens)
    if screen is None:
        return None
    left, top, right, bottom = screen

    margin = radius + sprite
    lo_x, hi_x = left + margin, right - margin
    lo_y, hi_y = top + margin, bottom - margin
    # A screen too small for the margins keeps its centre rather than raising
    # on an empty range, which is what _pick_target and place_hoop both do.
    if hi_x < lo_x:
        lo_x = hi_x = (left + right) / 2.0
    if hi_y < lo_y:
        lo_y = hi_y = (top + bottom) / 2.0

    clearance = TARGET_CLEARANCE_SPRITES * sprite
    keep_off = _avoid(avoid)
    candidates = [(lo_x + (hi_x - lo_x) * rng.random(),
                   lo_y + (hi_y - lo_y) * rng.random())
                  for _ in range(TARGET_TRIES)]

    def clear_of_others(spot):
        return all(math.hypot(spot[0] - x, spot[1] - y)
                   >= radius + other + sprite
                   for x, y, other in keep_off)

    def far_enough(spot):
        return math.hypot(spot[0] - here[0], spot[1] - here[1]) >= clearance

    # Three tiers, in the order the failures matter. Overlapping the basket is
    # a broken drawing; landing near the character is only a target that is
    # too easy; and where nothing sampled satisfies either, the furthest from
    # the character is still the best of what there was.
    room = [c for c in candidates if far_enough(c) and clear_of_others(c)]
    if not room:
        room = [c for c in candidates if clear_of_others(c)]
    if room:
        spot = rng.choice(room)
    else:
        spot = max(candidates,
                   key=lambda c: (c[0] - here[0]) ** 2 + (c[1] - here[1]) ** 2)
    return Target(spot[0], spot[1], rings, now)


# ── what a run of throws adds up to ────────────────────────────────────────

# How long a run of hits stays alive, measured from the last one.
#
# buddy_hoop.THROW_MEMORY, for buddy_idle.STREAK_MEMORY's reason: the temper
# holds a throw against you for ninety seconds, and credit for playing along
# that expired sooner would mean a character that forgives at one speed and
# congratulates at another. It is also comfortably longer than a run needs —
# a target lives TARGET_SECONDS = 20 s, so three hits in a row fit inside it.
COMBO_MEMORY = buddy_hoop.THROW_MEMORY

# How long the character may be held between a catch and the next throw before
# the rally is over. 3.5 s, quoted from the companion's DRAG_PATIENCE — the
# number cannot be imported, because usage-buddy-companion.py has a dash in
# its name and is not importable at all, which is the same reason buddy_idle
# and buddy_hoop quote it.
#
# It is that number and not one of its own because DRAG_PATIENCE is already
# the moment the character says put me down: past it, whatever is happening is
# not a rally any more, and the character is on record saying so.
JUGGLE_HOLD = 3.5


class Combo:
    """Hits in a row, and what breaks a row.

    What breaks it, decided rather than inherited:

      a throw that missed        breaks it, and this is the definition. It has
                                 to be a throw at a target that was up: a
                                 character thrown around a desktop with
                                 nothing to aim at has missed nothing.
      the target expiring        does not. buddy_idle.Streak makes the same
                                 call about the basket, and for the same
                                 reason: ending a run because the person
                                 walked away turns an offer into an
                                 obligation.
      being dragged, docked,
      caught, put down           does not. None of them is a throw at a
                                 target, and a counter that anything at all
                                 can reset is one the player cannot predict.
      silence                    does, after COMBO_MEMORY.

    Kept separate from the rally below, which is the other obvious design and
    the wrong one. Merging them needs "landing breaks the run — unless the run
    is made of hits, because a hit always ends with the character on the
    floor", which is two rules sharing one name. Two counters are honest
    because they are never announced at the same moment: a combo is said when
    something is hit, a rally when the character is caught.
    """

    def __init__(self, memory=COMBO_MEMORY):
        self.memory = float(memory)
        self.best = 0
        self._run = 0
        self._at = None

    def run(self, now):
        """The run still alive at `now`, expiring it on the way past.

        Pruned on read rather than in a sweep of its own: buddy_hoop.Temper
        and buddy_idle.Streak both do it here, and it happens on the only
        path that reads the number.
        """
        if self._at is None:
            return 0
        if float(now) - self._at > self.memory:
            self._run = 0
            self._at = None
        return self._run

    def hit(self, now):
        """Record a hit. The run it makes."""
        now = float(now)
        self._run = self.run(now) + 1
        self._at = now
        self.best = max(self.best, self._run)
        return self._run

    def missed(self):
        """A throw that came to rest without scoring. The run is over."""
        self._run = 0
        self._at = None
        return 0


Catch = namedtuple("Catch", "run best force points")


class Juggle:
    """Catches in a row: thrown, caught in mid-air, thrown again.

    The catch itself already works and is not this module's doing: the
    companion's mousePressEvent sets `self.flying = False`, so a hand on the
    character during a throw ends the flight and becomes a drag. What was
    missing is the verdict — whether that was a catch worth counting.

    Where the line is, and why it is not a number of bounces:

      still on the arc it was
      thrown on                  counts. Nothing has hit it yet.
      after an impact that left
      it above lift_speed        counts. It can still rise its own height, so
                                 it is a body in the air and catching it is
                                 timing.
      after an impact that left
      it below that              does not. RESTITUTION is 0.55, so the speed
                                 falls off geometrically and the tail of a
                                 flight is a body hopping a few pixels along
                                 the floor. Scooping it up there is not
                                 juggling and counting it would make the whole
                                 rally free.

    A bounce count would have been the obvious rule and it is the wrong one:
    the same third bounce is a body still 458 px in the air after a throw at
    the ceiling and a body vibrating on the floor after a lob, so the number
    that means "the flight is over" is a speed, and it is the one lift_speed
    already answers for the force bands.

    What breaks the rally:

      it lands uncaught           breaks it. That is what dropping is.
      it is put down rather than
      thrown                      breaks it. A release under THROW_MIN_SPEED
                                  is a placement, and without this rule a
                                  rally could be parked indefinitely by
                                  setting the character on the desktop.
      it is held past JUGGLE_HOLD breaks it. Juggling is catch and throw; past
                                  the point where the character itself starts
                                  asking to be put down, whatever this is, it
                                  is not a rally.
      a miss, a basket, the
      target expiring             do not. They belong to the other counter.
    """

    def __init__(self, sprite_px, screen_px=TALLEST_SCREEN_PX,
                 hold=JUGGLE_HOLD):
        self.sprite_px = float(sprite_px)
        self.screen_px = float(screen_px)
        self.hold = float(hold)
        self.best = 0
        self._run = 0
        self._flying = False
        self._held_at = None
        self._impact = None

    def run(self, now):
        """The rally still alive at `now`, expiring a held one on the way."""
        if (self._held_at is not None
                and float(now) - self._held_at > self.hold):
            self._run = 0
            self._held_at = None
        return self._run

    def live(self, now):
        """Whether a rally is going on right now.

        This is what suspends the getaway, so it is deliberately narrow: a
        rally exists only while at least one catch has been made and the
        character is either in the air or freshly in hand.
        """
        return self.run(now) > 0 and (self._flying or self._held_at is not None)

    def launched(self, now, vel):
        """A release that was a throw. The rally it continues, or 0.

        Continuing is the default and the interesting case: the run is only
        cleared here when the hold before it went on too long, which run()
        has already decided.
        """
        run = self.run(now)
        self._flying = True
        self._held_at = None
        self._impact = None
        return run

    def placed(self):
        """A release that was not a throw. Putting it down ends the rally."""
        self._run = 0
        self._flying = False
        self._held_at = None
        self._impact = None
        return 0

    def bounced(self, speed):
        """An impact during the flight, with the speed it left behind.

        Only the last one is kept, which is enough: RESTITUTION is below 1, so
        the sequence only ever falls, and once it is under lift_speed no later
        impact can put it back over.
        """
        try:
            value = float(speed)
        except (TypeError, ValueError):
            return
        if math.isfinite(value):
            self._impact = value

    def airborne(self):
        """Whether the flight is still one a catch could be made out of."""
        if not self._flying:
            return False
        if self._impact is None:
            return True
        return self._impact >= lift_speed(self.sprite_px)

    def caught(self, now, speed):
        """A hand on it during a flight. The Catch, or None for a scoop.

        A scoop — picking it up once the flight is over in all but name — is
        not merely uncounted, it ends the rally. Leaving the run standing
        would mean a rally could be kept alive by letting the character roll
        to a stop and then picking it up, which is the opposite of the skill
        the count is for.
        """
        if not self._flying:
            return None
        alive = self.airborne()
        self._flying = False
        self._held_at = float(now)
        if not alive:
            self._run = 0
            self._held_at = None
            return None
        self._run = self.run(now) + 1
        self.best = max(self.best, self._run)
        force = force_band(speed, self.sprite_px, self.screen_px)
        return Catch(run=self._run, best=self.best, force=force,
                     points=self._worth(force))

    def dropped(self):
        """The flight reached the floor with nobody catching it."""
        self._run = 0
        self._flying = False
        self._held_at = None
        self._impact = None
        return 0

    def _worth(self, force):
        """What a catch is worth: its band's place in FORCES, from one.

        Difficulty is the speed the body was doing when the hand closed on it,
        not the speed it left at — a hard throw caught at the top of its arc
        is barely moving, and catching it there is easy. Anything under
        THROW_MIN_SPEED has no band at all and is worth the minimum: below the
        speed the character walks at, catching it is not a skill.

        A rally that pays the same for every catch is a rally everybody plays
        gently, which is a dead rally.
        """
        return 1 if force is None else FORCES.index(force) + 1


class Record:
    """The longest throw so far, in pixels.

    Straight from where it was let go to where it came to rest, and not the
    length of the path: bounces would inflate it, and a body skidding along
    the floor would go on adding to it after the throw was over. Displacement
    is also the number somebody watching can check against the screen they are
    looking at.

    Strictly greater, never equal. A tie is not a new record, and `>=` here
    would announce one on every repeat of the same throw — which on a desktop
    where the character often lands in the same corner is most of them.
    """

    def __init__(self, best=0.0):
        self.best = self._clean(best) or 0.0

    @staticmethod
    def _clean(distance):
        try:
            value = float(distance)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value) or value < 0.0:
            return None
        return value

    def log(self, distance):
        """Record a throw. True only if it beat the best there was."""
        value = self._clean(distance)
        if value is None or value <= self.best:
            return False
        self.best = value
        return True

    def to_dict(self):
        """What the companion writes. See the note at the top of the file."""
        return {"best_px": self.best}

    @classmethod
    def from_dict(cls, data):
        """A record out of what was on disk, junk and all.

        Anything unreadable is a record of zero rather than an exception: the
        file is state the program wrote for itself, and refusing to start
        because it got corrupted would be a worse bug than losing a number
        that can be re-earned by throwing the character across the screen.
        """
        try:
            return cls(data.get("best_px", 0.0))
        except AttributeError:
            return cls(0.0)


# ── what the companion asks for on a frame ─────────────────────────────────

Throw = namedtuple("Throw", "distance force record best")

GameState = namedtuple(
    "GameState",
    "visible centre radius expired hits misses combo rally record")


class ThrowGame:
    """The target, the record, the hit combo and the rally, in one object.

    One object because they overlap in exactly two places and both are the
    kind of thing that goes wrong when two objects each own half of it: the
    throw that ends a rally is the same throw that sets a record, and the
    suspension of the getaway is the union of two answers that must be read
    together.

    The seam, in the order the companion already has the events:

      release        released(now, position, vel) -> force band or None
      each step      landed(was, now_pos, now)    -> Hit or None
      an impact      bounced(speed)
      a press        caught(now, speed)           -> Catch or None
      resting        settled(now, position)       -> Throw
      after that     offer(now, position, screens, rng, avoid) -> Target|None
      every frame    state(now), suspends_getaway(now)

    `rings` is what target_rings answers; None means the drawing has not
    landed yet, and then the game keeps the record, the rally and the force
    bands and never offers a target. That is not an error, and it is how this
    ships before the art does.
    """

    def __init__(self, sprite_px, rings=None, screen_px=TALLEST_SCREEN_PX,
                 record=None):
        self.sprite_px = float(sprite_px)
        self.screen_px = float(screen_px)
        self.rings = tuple(rings) if rings else None
        self.target = None
        self.record = record if record is not None else Record()
        self.combo = Combo()
        self.juggle = Juggle(self.sprite_px, self.screen_px)
        self.hits = 0
        self.misses = 0
        self.points = 0
        self._launch = None
        self._force = None

    # ── the throw ──

    def released(self, now, position, vel):
        """A release. The force band, or None when it was a placement.

        The band is remembered, because the flight that follows is judged
        against it: settled() reports it back so the companion can react to
        how hard the throw was at the moment it lands.
        """
        force = throw_force(vel, self.sprite_px, self.screen_px)
        self._force = force
        if force is None:
            self._launch = None
            self.juggle.placed()
            return None
        self._launch = (float(position[0]), float(position[1]))
        self.juggle.launched(now, vel)
        return force

    def bounced(self, speed):
        """An impact, with the speed the body left it with."""
        self.juggle.bounced(speed)

    def caught(self, now, speed):
        """A hand on the character in mid-flight. The Catch, or None."""
        return self.juggle.caught(now, speed)

    def settled(self, now, position):
        """The flight is over. What it was worth.

        Three things end here and they end together on purpose: the distance
        goes to the record, the rally is over because nobody caught it, and if
        a target was up and unscored the throw was a miss. Splitting them
        across three calls is three chances for the companion to make one of
        them and forget another, and the one it would forget is the miss.
        """
        self.juggle.dropped()
        distance = 0.0
        if self._launch is not None:
            distance = math.hypot(float(position[0]) - self._launch[0],
                                  float(position[1]) - self._launch[1])
        beaten = self.record.log(distance) if self._launch is not None else False
        if self.live(now):
            self.misses += 1
            self.combo.missed()
        self._launch = None
        return Throw(distance=distance, force=self._force, record=beaten,
                     best=self.record.best)

    # ── the target ──

    def offer(self, now, position, screens, rng=random, avoid=()):
        """Put a target up after a throw. The new one, or None.

        None when there is no drawing, when one is already up, and when the
        last release was a placement rather than a throw — a character set
        down on the desktop has not asked for a game.

        Called when the flight settles rather than when it is released, so the
        throw that summoned the target cannot also score it. A target that
        materialised around a body already in flight would pay out for a
        coincidence, and the first thing anybody would learn is that aiming is
        optional.
        """
        if self.rings is None or self._force is None or self.live(now):
            return None
        target = place_target(position, screens, self.sprite_px, self.rings,
                              now, rng, avoid)
        if target is None:
            return None
        self.target = target
        return target

    def summon(self, now, position, screens, rng=random, avoid=()):
        """Put a target up because the player asked for one. The new one, or None.

        `offer` refuses when the last release was a placement, because setting
        the character down is not asking for a game. A menu entry *is* the
        asking, so that gate does not apply to it — but the others still do:
        one target at a time, and none without a drawing to hang.

        Separate from `offer` rather than a flag on it, because the two answer
        different questions. `offer` asks whether a throw earned a target;
        this asks nothing and grants one. Folding them together would mean a
        caller could accidentally hand the throw path a flag that skips the
        gate the throw path exists to enforce.
        """
        if self.rings is None or self.live(now):
            return None
        target = place_target(position, screens, self.sprite_px, self.rings,
                              now, rng, avoid)
        if target is None:
            return None
        self.target = target
        return target

    def live(self, now):
        """Whether a target is on screen right now."""
        return self.target is not None and not self.target.expired(now)

    def expired(self, now):
        """Whether the target that was offered ran out unscored.

        Kept rather than dropped on the way past, so the companion can tell
        "there was never one" from "there was one and nobody threw at it" —
        the first has nothing to say and the second has a line. The stale
        object is replaced by the next offer, so nothing accumulates.
        """
        return self.target is not None and self.target.expired(now)

    def landed(self, start, end, now):
        """Judge one step of a flight. A Hit exactly once, on the step that
        scored, and None on every other.

        The target comes down on a hit — it has been used — which is also what
        lets the next throw put a new one up.
        """
        if not self.live(now):
            return None
        hit = self.target.score(start, end, self.sprite_px)
        if hit is None:
            return None
        self.target = None
        self.hits += 1
        self.points += hit.points
        run = self.combo.hit(now)
        return hit._replace(combo=run, best=self.combo.best)

    def clear(self):
        """Take the target down unscored: the game is being put away."""
        self.target = None

    # ── what the two halves have to agree about ──

    def suspends_getaway(self, now):
        """While a game is on, buddy_hoop's getaway waits.

        The union of the two, in one call, because the companion asks the
        question once. Suspension and nothing else: neither the target nor the
        rally touches the temper's count, so the moment the game stops the
        character is exactly as angry as it was. buddy_hoop's basket is still
        the only thing that forgives it, which is what keeps the basket worth
        offering.
        """
        return self.live(now) or self.juggle.live(now)

    def state(self, now):
        """Everything the companion needs on a frame, in one read.

        One call so the frame path cannot catch a half-updated game — the
        target already expired but the getaway still suspended by it, or the
        rally counted but not yet timed out — which is the shape of bug that
        only appears on the frame something goes away.
        """
        visible = self.live(now)
        target = self.target if visible else None
        return GameState(
            visible=visible,
            centre=target.centre if target is not None else None,
            radius=target.radius if target is not None else None,
            expired=self.expired(now),
            hits=self.hits,
            misses=self.misses,
            combo=self.combo.run(now),
            rally=self.juggle.run(now),
            record=self.record.best,
        )
