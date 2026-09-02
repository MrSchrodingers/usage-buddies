"""Being thrown once is a joke. Being thrown twice earns an answer.

Two halves of the same gag, and the same shape as buddy_focus and
buddy_actions: no Qt, no timers, no clock of its own. Time, geometry and the
pointer's position all arrive as arguments, and anything this cannot know is
None rather than a plausible number. The companion owns the frame clock, the
window and the painting; this owns the arithmetic and the verdicts.

  temper — throws are remembered with a timestamp inside a window. More than
           one inside it and the character has had enough: it runs to where
           the cursor is and leaves with it.
  hoop   — held for long enough, it offers a basket instead. While the basket
           is on screen the getaway is suspended, because the basket is an
           offer: throw me at that instead. Score and the temper is paid off;
           miss, or ignore it until it expires, and the getaway is waiting.

The coordinate convention is buddy_actions', and is the same throughout:
positions are the sprite's top-left corner, and `bounds` is the rectangle of
allowed top-left corners, (min_x, min_y, max_x, max_y), already inset by the
sprite size. Screens are (left, top, width, height), which is what
Companion._screen_rects hands out. The hoop's own position is the centre of
its opening, because that is what a hit is measured against.
"""
from __future__ import annotations

import math
import random
from collections import namedtuple

# ── having been thrown once too often ──────────────────────────────────────

# How long a throw is held against you. The same ninety seconds the companion
# already uses for DRAG_MEMORY, deliberately: being hauled around and being
# thrown are the same complaint at two speeds, and measuring them on two
# different clocks would mean a character that forgives one while still
# holding the other.
THROW_MEMORY = 90.0

# Thrown more than once inside that window and it stops being funny. Two, not
# three: the first throw is the discovery that the character can be thrown,
# and the second is a decision. The same shape as DRAG_TUG_AFTER, which is
# also 2, and for the same reason.
FURY_AFTER = 2

# How old a reading of the pointer may be before running at it is running at
# where it used to be.
#
# MEASURED on the desktop this was written for (Plasma on Wayland, XWayland
# for this process): QCursor.pos() and xdotool both read XWayland's shadow of
# the pointer, and that shadow stops following the pointer while it is over a
# native Wayland window. It cannot be told apart from a pointer that is simply
# not moving, so no amount of reading it twice settles the question.
#
# So the position is not read here at all — it is a parameter, and it comes
# with the age of the reading. The one reading on this desktop that is fresh
# by construction is the one a mouse event carried: the release that ended the
# throw arrived with a pointer position from the input stack rather than from
# a query, and its age is `now - the moment of that event`, which the caller
# already has. Half a second is fifteen frames at the companion's active rate,
# far more than the same call stack needs, and short enough that a pointer
# moving at any ordinary speed has not left the neighbourhood.
CURSOR_STALE_AFTER = 0.5


class Temper:
    """How many times it has been thrown lately, and whether that is too many.

    Nothing here decays gradually. A throw either happened inside the window
    or it did not, which is the same rule the companion's own recent_drags
    uses and is the only one that can be explained to somebody watching: two
    throws close together, and it comes for the mouse.
    """

    def __init__(self, memory=THROW_MEMORY, threshold=FURY_AFTER):
        self.memory = float(memory)
        self.threshold = int(threshold)
        self._throws = []

    def thrown(self, now):
        """Record a throw. Returns how many are in the window including it."""
        self._throws.append(float(now))
        return self.count(now)

    def count(self, now):
        """Throws still inside the window, old ones dropped as they are seen.

        Pruning here rather than in a sweep of its own means a companion left
        running for days cannot accumulate one entry per throw it has ever
        taken, and it happens on the only path that reads the list.
        """
        self._throws = [t for t in self._throws if now - t <= self.memory]
        return len(self._throws)

    def furious(self, now):
        return self.count(now) >= self.threshold

    def forgive(self):
        """Wipe it. A basket scored pays the debt off in full.

        Not a decrement: the point of the hoop is that playing along ends the
        argument, and subtracting one throw from three would leave a character
        that comes for the mouse on the next throw anyway, which reads as the
        game having done nothing.
        """
        self._throws = []


def usable_cursor(cursor, age, area=None):
    """The pointer position this is willing to run at, or None.

    `age` has no default on purpose. It is the seconds since the reading was
    taken, and None means the caller cannot say — which is answered with None,
    a refusal, rather than with a guess. The refusal costs the alignment and
    nothing else: the getaway still happens, starting where the character
    stands, which is exactly the behaviour that shipped before this existed.
    Running at a reading that might be a frozen shadow costs that same
    displacement *plus* a sprint across the desktop to somewhere the pointer
    is not, which from the outside is the character being broken.

    Handing in 0.0 for a position obtained from QCursor.pos() is a claim this
    module cannot check and that the measurement above says is false on this
    desktop. The honest source is the position a mouse event carried, with the
    age measured from that event.

    `area` is the visible rectangle as (left, top, right, bottom) when the
    caller has one. It rejects a reading that is not on this desktop at all —
    junk, a coordinate from another machine's display — which is the only part
    of staleness that can be detected from the number itself.
    """
    try:
        x, y = float(cursor[0]), float(cursor[1])
    except (TypeError, ValueError, IndexError, KeyError):
        return None
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    if age is None:
        return None
    try:
        seconds = float(age)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(seconds) or seconds < 0.0 or seconds > CURSOR_STALE_AFTER:
        return None
    if area is not None:
        try:
            left, top, right, bottom = (float(v) for v in area)
        except (TypeError, ValueError):
            return None
        if not (left <= x <= right and top <= y <= bottom):
            return None
    return (x, y)


def chase_target(cursor, age, sprite_px, bounds):
    """Where to stand so the pointer is under the character, or None.

    This is the leg that fixes a measured defect. The carry moves the pointer
    by the character's own per-frame delta and never by an absolute position —
    it cannot, see Companion._tug — so the pointer arrives displaced from the
    character by exactly the gap between them at the moment the run began.
    Starting the run *on* the cursor makes that gap zero, and the pointer
    arrives where the character does.

    None is the answer to every reading that cannot be trusted, and the caller
    treats all of them the same way: skip this leg and run from where it
    stands. A refusal is never worse than not having asked.

    The point returned is a top-left corner, so the sprite is centred on the
    cursor; it is clamped into `bounds`, which near an edge means the centre
    misses the cursor by up to half a sprite. That is the correct trade — the
    alternative is a corner outside the walking area, which the companion
    clamps anyway, one frame later and less predictably.
    """
    sprite = float(sprite_px)
    min_x, min_y, max_x, max_y = (float(b) for b in bounds)
    # The visible area is `bounds` grown by one sprite on the right and
    # bottom, and the whole rectangle is already inset from the screen edges;
    # a sprite of slack on every side puts that inset back, so a pointer
    # resting in the last few pixels of a screen still counts as being on it.
    area = (min_x - sprite, min_y - sprite,
            max_x + 2.0 * sprite, max_y + 2.0 * sprite)
    seen = usable_cursor(cursor, age, area)
    if seen is None:
        return None
    x = seen[0] - sprite / 2.0
    y = seen[1] - sprite / 2.0
    return (max(min_x, min(max_x, x)), max(min_y, min(max_y, y)))


# ── the basket ─────────────────────────────────────────────────────────────

# How long it has to be held before the basket is offered.
#
# The window this has to fit in is the companion's own and both ends of it are
# already fixed. DRAG_PATIENCE is 3.5 s — the point at which it starts saying
# put me down — and DRAG_TUG_ALWAYS is 10 s, at which the getaway fires with
# no cooldown and no forgiveness. The offer has to sit strictly between them:
# arriving with the complaint makes the two read as one event, and arriving
# after ten seconds means the getaway has already happened and there was never
# an offer at all. Six seconds is past the complaint and past DRAG_TUG_SECONDS
# (5 s, the first provocation tier, which the suspension below then converts
# from a retaliation into this offer), and it leaves four seconds of the ten
# to take the offer up in, which is two or three throws.
HOOP_AFTER = 6.0

# How long it stays there. It has to outlive the drag that produced it —
# nothing can be thrown until it is let go — and a throw's whole flight is
# under two seconds at this gravity, so twelve seconds is room for two or
# three attempts. It is also the reason there is an upper bound at all: the
# getaway is suspended while the basket is up, so a basket that never expired
# would mean holding the mouse down forever is a way to never be retaliated
# against, which is the loophole the getaway exists to close.
HOOP_SECONDS = 12.0

# How far from the character it appears, in sprite widths, centre to centre.
# A basket that appears on top of it is not a game — the character could walk
# there. Four sprites is 224 px at the measured sprite size, which is nearly
# three seconds of walking at WALK_SPEED and comfortably past the length of
# the drag gesture that produced it.
HOOP_CLEARANCE_SPRITES = 4.0

# How many places are tried before the clearance is given up on. Eight, and
# the same fallback the companion uses when it picks somewhere to run to: take
# the furthest of what was sampled. On a screen with no room for the clearance
# at all, the furthest legal spot is the best answer available, and refusing
# to place anything would silently remove the game on small displays.
HOOP_TRIES = 8

# How much wider than the drawing the hit area is, in sprites. Half a sprite
# is the sprite's own half-width, so the hit is scored when the drawing
# touches the ring rather than when the centre threads it: the total width
# that counts is the rim plus one whole sprite. That is deliberately generous
# — it is a joke, not darts — and it is the folded-in answer to the fact that
# a throw is integrated in steps of up to MAX_STEP (0.05 s), which at the
# speed ceiling is 120 px of travel per step.
HIT_SLACK_SPRITES = 0.5


def rim_width(art=None):
    """The width of the drawn opening in screen pixels, or None.

    The number is buddy_sprites' and is never repeated here: HOOP_RIM is the
    box around the hole, (left, top, width, height), in the art's own source
    pixels, and SCALE is what turns those into the pixels every position in
    this module is in. Written out again beside the thing that decides whether
    a throw scored, those numbers would be two truths, and they would diverge
    the first time the ring moved by a pixel.

    This is the one place the conversion happens, and it is here rather than
    in the companion because getting it wrong is invisible: a hit area sized
    in source pixels is half the width it should be, which reads as a basket
    that is simply hard to hit.

    None when the art has no hoop in it, which is not an error — the game does
    not offer a basket, and it starts working the moment the drawing lands.
    The import is inside the function so this module keeps its own promise of
    importing nothing that can fail.
    """
    if art is None:
        try:
            import buddy_sprites as art
        except ImportError:
            return None
    box = getattr(art, "HOOP_RIM", None)
    if box is None:
        return None
    try:
        scale = float(getattr(art, "SCALE", 1))
        # A box, as the art declares it, or a bare width from an art that
        # decided to publish only the one number.
        source = float(box[2]) if isinstance(box, (tuple, list)) else float(box)
    except (TypeError, ValueError, IndexError):
        return None
    width = source * scale
    return width if width > 0 else None


def _rect(screen):
    """(left, top, right, bottom) from an (x, y, width, height), or None."""
    try:
        left, top, width, height = (float(v) for v in screen)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return (left, top, left + width, top + height)


def _screen_for(point, screens):
    """The screen a point is on, or the nearest one, as a rectangle.

    Nearest rather than None, and this is the whole reason the union of the
    screens is not used anywhere here: the companion documents that the union
    contains regions belonging to no display — the two monitors measured on
    this machine are 1234 and 1200 pixels tall — and a character standing in
    one of those has no screen of its own. It still has to be offered a game,
    and the nearest real display is where that game goes.
    """
    rects = [r for r in (_rect(s) for s in screens or ()) if r is not None]
    if not rects:
        return None
    for left, top, right, bottom in rects:
        if left <= point[0] < right and top <= point[1] < bottom:
            return (left, top, right, bottom)
    return min(rects, key=lambda r: (((r[0] + r[2]) / 2.0 - point[0]) ** 2
                                     + ((r[1] + r[3]) / 2.0 - point[1]) ** 2))


def _segment_distance(point, start, end):
    """Shortest distance from a point to the segment between two points."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    if dx == 0.0 and dy == 0.0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    t = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(point[0] - (start[0] + t * dx),
                      point[1] - (start[1] + t * dy))


class Hoop:
    """A basket on the desktop: where the opening is, and when it appeared.

    `x` and `y` are the centre of the opening rather than a corner, because
    the centre is what a hit is measured against and a corner would have to be
    converted back at every call site.

    `rim` is the width of the drawn opening, in the same pixels as everything
    else here. It is carried rather than known: the drawing lives in
    buddy_sprites and the number belongs with it, so repeating it here would
    be two numbers to keep in step and one of them would drift. rim_width()
    is the one conversion from the art's own units.
    """

    def __init__(self, x, y, rim, shown_at):
        self.x = float(x)
        self.y = float(y)
        self.rim = float(rim)
        self.shown_at = float(shown_at)

    @property
    def centre(self):
        return (self.x, self.y)

    def hit_radius(self, sprite_px):
        """How close the sprite's centre has to pass. See HIT_SLACK_SPRITES."""
        return self.rim / 2.0 + float(sprite_px) * HIT_SLACK_SPRITES

    def expired(self, now, life=HOOP_SECONDS):
        return now - self.shown_at >= float(life)

    def crossed(self, start, end, sprite_px):
        """Whether a sprite moving from `start` to `end` went through it.

        The travel is treated as a segment and not as its endpoints, and that
        is the whole reason this method exists. buddy_actions integrates a
        throw in steps of up to MAX_STEP = 0.05 s, and at THROW_MAX_SPEED that
        is 120 px in one step — more than two sprite widths. A test that asks
        only whether the sprite is inside the hit area on this frame misses
        every throw fast enough to be worth watching, which is precisely the
        throws somebody aiming at a basket makes.

        `start` and `end` are top-left corners, the companion's convention;
        the centres are what travel.
        """
        sprite = float(sprite_px)
        half = sprite / 2.0
        a = (float(start[0]) + half, float(start[1]) + half)
        b = (float(end[0]) + half, float(end[1]) + half)
        return _segment_distance(self.centre, a, b) <= self.hit_radius(sprite)


def place_hoop(position, screens, sprite_px, rim, now, rng=random):
    """Somewhere on one screen to put a basket, or None.

    Three constraints, and every one of them is a way the placement is wrong
    rather than a preference:

      one screen  — never the union of them. The union has regions that belong
                    to no display, and a basket drawn in one is invisible
                    while looking perfectly correct to the code.
      the screen the character is on — not a random one. The flight is
                    ballistic and bounded; the desktop measured here is
                    4115 px across two monitors and the speed ceiling is
                    2400 px/s under a gravity that ends the arc in about a
                    second and a half, so a basket on the other monitor is a
                    target that cannot be reached. A game that cannot be won
                    is not an offer.
      clear of the edges — by half the drawing, so it is wholly on screen, and
                    by a whole sprite on top of that, so there is room for the
                    sprite to reach it from the outside. A basket flat against
                    an edge can only be scored from off the screen.
      clear of the character — HOOP_CLEARANCE_SPRITES, or the furthest of what
                    was sampled when no screen has that much room.

    None when there is no screen to put it on, or no drawing to put there.
    """
    if not rim or float(rim) <= 0:
        # No art, no basket. A hit area with nothing drawn in it is an
        # invisible target, which is worse than no game at all.
        return None
    sprite = float(sprite_px)
    rim = float(rim)
    here = (float(position[0]) + sprite / 2.0, float(position[1]) + sprite / 2.0)
    screen = _screen_for(here, screens)
    if screen is None:
        return None
    left, top, right, bottom = screen

    margin = rim / 2.0 + sprite
    lo_x, hi_x = left + margin, right - margin
    lo_y, hi_y = top + margin, bottom - margin
    # A screen too small for the margins keeps its centre rather than raising
    # on an empty range: the companion's own _pick_target clamps the same way.
    if hi_x < lo_x:
        lo_x = hi_x = (left + right) / 2.0
    if hi_y < lo_y:
        lo_y = hi_y = (top + bottom) / 2.0

    clearance = HOOP_CLEARANCE_SPRITES * sprite
    candidates = [(lo_x + (hi_x - lo_x) * rng.random(),
                   lo_y + (hi_y - lo_y) * rng.random())
                  for _ in range(HOOP_TRIES)]
    far = [c for c in candidates
           if math.hypot(c[0] - here[0], c[1] - here[1]) >= clearance]
    if far:
        spot = rng.choice(far)
    else:
        spot = max(candidates,
                   key=lambda c: (c[0] - here[0]) ** 2 + (c[1] - here[1]) ** 2)
    return Hoop(spot[0], spot[1], rim, now)


# ── what the companion asks for on a frame ─────────────────────────────────

HoopState = namedtuple("HoopState", "visible centre rim expired score misses angry")


class HoopGame:
    """The temper, the basket in front of it, and the score.

    One object so the two halves cannot disagree about which is in charge.
    The suspension is the only place they meet: while a basket is on screen
    the getaway does not fire, because the basket is the alternative being
    offered and retaliating in the middle of an offer withdraws it.

    `rim` is the width of the drawn opening in screen pixels, which is what
    rim_width() answers; None means there is no drawing to aim at. That is not
    an error: the game simply never offers a basket, the temper still works,
    and the drawing being added later turns the game on with no change here.
    """

    def __init__(self, sprite_px, rim=None, temper=None):
        self.sprite_px = float(sprite_px)
        self.rim = None if not rim else float(rim)
        self.temper = temper if temper is not None else Temper()
        self.hoop = None
        self.score = 0
        self.misses = 0

    # ── the temper ──

    def thrown(self, now):
        """Record a throw. Returns how many are inside the memory window."""
        return self.temper.thrown(now)

    def should_chase(self, now):
        """Whether it is done being thrown and is coming for the pointer.

        The suspension is here rather than at the call site, because this is
        the one question the companion asks and both halves have to be in the
        answer. A basket on screen suspends the getaway outright: it was
        offered a second ago, and taking the mouse while it is still up is the
        offer being withdrawn before anybody could accept it.
        """
        return self.temper.furious(now) and not self.live(now)

    # ── the basket ──

    def offer(self, now, held_for, position, screens, rng=random):
        """Put a basket up if it has been held long enough. The new one, or None.

        None both when it is too early and when one is already up, so the
        caller can hang a sentence off the return value without it repeating
        once per frame for as long as the basket lasts.
        """
        if self.rim is None or held_for < HOOP_AFTER or self.live(now):
            return None
        hoop = place_hoop(position, screens, self.sprite_px, self.rim, now, rng)
        if hoop is None:
            return None
        self.hoop = hoop
        return hoop

    def live(self, now):
        """Whether a basket is on screen right now."""
        return self.hoop is not None and not self.hoop.expired(now)

    def expired(self, now):
        """Whether the basket that was offered has run out unscored.

        Kept rather than dropped on the way past, so the companion can tell
        "there was never one" from "there was one and it was ignored" — the
        first has nothing to say and the second has a line. The stale object
        is replaced by the next offer, so nothing accumulates.
        """
        return self.hoop is not None and self.hoop.expired(now)

    def suspends_getaway(self, now):
        """While the basket is up, the getaway waits. Named for what it does."""
        return self.live(now)

    def landed(self, start, end, now):
        """Judge one step of a flight. True exactly once, on the step that scored.

        The basket comes down on a hit — it has been used — which is also what
        ends the suspension, so the character is free to be furious again the
        next time it is thrown twice.
        """
        if not self.live(now):
            return False
        if not self.hoop.crossed(start, end, self.sprite_px):
            return False
        self.hoop = None
        self.score += 1
        # Scoring pays the debt off. This is the only thing that clears the
        # temper: playing along is the way out, and there is no other.
        self.temper.forgive()
        return True

    def missed(self):
        """A flight that ended without scoring. Bookkeeping, and nothing else.

        Pointedly not touching the temper: a miss leaves every throw that has
        been taken still counted, so missing is not a way of working the anger
        off. The counter is here because the character has something to say
        about a run of them.
        """
        self.misses += 1
        return self.misses

    def clear(self):
        """Take the basket down without scoring it: the game is over."""
        self.hoop = None

    def state(self, now):
        """Everything the companion needs on a frame, in one call.

        A single read so the frame path cannot see a half-updated game — the
        basket already expired but the anger still suspended, or the other way
        round — which is the shape of bug that only appears on the frame the
        basket goes away.
        """
        visible = self.live(now)
        hoop = self.hoop if visible else None
        return HoopState(
            visible=visible,
            centre=hoop.centre if hoop is not None else None,
            rim=hoop.rim if hoop is not None else None,
            expired=self.expired(now),
            score=self.score,
            misses=self.misses,
            angry=self.temper.furious(now),
        )
