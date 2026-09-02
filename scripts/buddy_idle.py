"""What the character does when nothing has happened, and what it remembers.

Four parts, all in the shape of buddy_focus and buddy_hoop: no Qt, no timers,
no clock of its own. Time arrives as an argument, randomness arrives as an
`rng` the caller can pin, and anything this cannot know is None rather than a
plausible number. The companion owns the frame clock, the painting and the
words; this owns the timing and the verdicts.

  Boredom  the one part here that inverts the rule the project was built on.
           Every line the companion says today is bound to a measured trigger
           — it is the sentence in the README and the reason this is not
           Clippy — and this one is bound to nothing having happened for long
           enough, which is what a Bonzi does. It is off by default and the
           argument for that is at BORED_DEFAULT.
  Antics   movement with no sentence attached: the cheap thing that fills the
           gap between two events, so the character reads as alive without
           spending the expensive thing, which is speech.
  Streak   the memory between baskets that buddy_hoop does not keep. It counts
           hits and misses; what it cannot say is whether this one was the
           third in a row, and the third in a row is not the first.
  Egg      the companion has no easter egg; the widget has one (five taps on
           the header mascot, plasmoid/contents/ui/main.qml). The hard half is
           not the reaction, it is finding a gesture that is not already
           spoken for — see the collision table above class Egg.

Every number quoted here from usage-buddy-companion.py is quoted, not
imported: that file is a script with a dash in its name and cannot be
imported at all. buddy_hoop restates DRAG_PATIENCE and DRAG_TUG_ALWAYS the
same way and for the same reason. Where a number belongs to a module that can
be imported, it is imported.
"""
from __future__ import annotations

import random
from collections import namedtuple

import buddy_focus
import buddy_hoop

# ── nothing has happened for long enough that that is itself the news ──────

# The switch, and which way it points when nobody has touched it.
#
# Off. The founding rule is written in the README, in this program's own
# docstring and in Brain: every line is bound to a measured trigger. The mode
# the README tells people to leave on is `alerts only`, which speaks solely
# when a session needs them, and boredom is the inversion of precisely that
# mode — the character talking with nothing to report. Defaulting it on would
# change what the recommended mode does on every existing installation at the
# next upgrade, without anybody asking for it, and the README already on their
# disk would then describe a different program. Turning it on is one flag;
# turning it back off, for somebody who never asked for it, is a bug report.
#
# The other half of the argument is that the cost of it being off is small.
# The antics below are on by default and they are the part that makes a
# desktop pet read as alive; what boredom adds is a sentence, which is the one
# thing this project has always been careful with.
BORED_DEFAULT = False

# How rare is rare. This is the number the whole part exists to defend, so it
# is the one that is declared and the gap below is derived from it rather than
# the other way round.
#
# Two an hour is one remark per half hour of a desktop nobody has touched. The
# failure this project was built against is a mascot that opens its mouth
# every couple of minutes; that is thirty an hour, fifteen times this.
BORED_PER_HOUR = 2

# ...which is a floor on the interval between two of them.
#
# Stated as a floor rather than as a cap on a sliding window because that is
# what it honestly is: two remarks exactly BORED_GAP apart put a third exactly
# an hour after the first, so a window drawn from one remark to another can
# hold three. The hour anybody actually counts starts when the desktop was
# last touched, and that one holds BORED_PER_HOUR.
BORED_GAP = 3600.0 / BORED_PER_HOUR

# How long nothing has to have happened first. Ten minutes, and the number is
# not invented here: sessions-probe.py calls a session `idle` at
# IDLE_SECONDS = 600 — no transcript write for ten minutes with the process
# still alive. That is this repository's one measured answer to how long
# silence has to last before the silence is itself a fact worth reporting, and
# reusing it means the character's patience and the collector's are the same
# number, decided once.
BORED_AFTER = 600.0

# The roll, once per opportunity, so the remark is not a metronome.
#
# The companion polls every POLL_MS = 20 s, so one chance in ten puts the
# remark on average two hundred seconds after it first becomes possible: a
# ninth of the gap, enough that two runs of the same untouched desktop do not
# produce it in the same minute. A probability can only ever make this rarer,
# which is exactly why the ceiling above is enforced by the gap and not by
# this — a rarity that depends on a coin is a rarity that can come up heads
# ten times.
BORED_CHANCE = 0.1


class Boredom:
    """Whether the character may say something with nothing to say.

    Three gates, and the order matters. Anything that actually happened wins:
    a measured line going out this cycle, or a silence that was asked for, is
    the world doing something, and either one restarts the clock rather than
    merely suppressing this. Then the switch. Then the two clocks — how long
    nothing has happened, and how long since the last time this spoke — and
    only then the coin.

    `due` records the remark it grants. That is deliberate, and it is the one
    place in this module where a read mutates: splitting it into a predicate
    and an acknowledgement leaves a caller free to forget the second half, and
    a caller that forgets it gets a character that talks on every poll
    forever. That is the exact failure this class exists to make impossible,
    so it is not left to the call site.
    """

    def __init__(self, enabled=BORED_DEFAULT, after=BORED_AFTER, gap=BORED_GAP,
                 chance=BORED_CHANCE):
        self.enabled = bool(enabled)
        self.after = float(after)
        self.gap = float(gap)
        self.chance = float(chance)
        # None, not 0.0: the clock is read as `now - quiet_since`, and from
        # zero that is the age of the monotonic clock — a companion three
        # seconds old would already have been bored for a week. The first call
        # sets it, which is also the moment the character appeared.
        self._quiet_since = None
        self._spoke_at = None

    def happened(self, now):
        """Something reached the person. Start the silence over.

        Called for anything the character did or had done to it: a line that
        went into the bubble, a hand on it, a folder dropped on it, a basket.
        Boredom is measured from the last of those, not from the last poll.
        """
        self._quiet_since = float(now)

    @property
    def waited(self):
        """The moment the current silence began, or None before the first call."""
        return self._quiet_since

    def due(self, now, silenced=False, trigger=False, rng=random):
        """Whether to say something unprompted right now. Records a True.

        `silenced` is the answer to buddy_focus.FocusSession.silences(now), or
        anything else that was a request for quiet — the quiet hours, or
        `alerts only` if the caller chooses to let this through in that mode at
        all. It restarts the clock rather than suppressing the remark, because
        silence that was asked for is not silence that accumulated: a block
        that ran twenty-five minutes must not be cashed in for a remark on the
        first poll after it ends.

        `trigger` says a measured line is going out this cycle. Then there is
        nothing to be bored about — something happened, and the character is
        about to talk about it. Speaking twice would also stack two bubbles in
        the same poll, and the second would replace the first.
        """
        now = float(now)
        if self._quiet_since is None:
            self._quiet_since = now
            return False
        if trigger or silenced:
            self._quiet_since = now
            return False
        if not self.enabled:
            return False
        if now - self._quiet_since < self.after:
            return False
        if self._spoke_at is not None and now - self._spoke_at < self.gap:
            return False
        if rng.random() >= self.chance:
            return False
        self._spoke_at = now
        self._quiet_since = now
        return True


# ── movement with no sentence attached ─────────────────────────────────────

# How long a pose is held. The companion already has a measured answer to how
# long a pose has to be up to be read — MOOD_SECONDS = 4.0, the clip a line is
# delivered in, "long enough to be read next to the sentence that caused it".
# An antic has no sentence beside it, so it needs at least as much, and no
# more: a pose held past four seconds stops reading as a beat and starts
# reading as the character's new state.
ANTIC_POSE_SECONDS = 4.0

# The ceiling on one that walks, not its length — it ends when the walk ends
# or when this runs out, whichever comes first. At WALK_SPEED = 78 px/s eight
# seconds is about 620 px, which is a lap of a good part of one screen and
# back, and it is the guard against the other case: a route the companion
# clamps to somewhere it is already standing would otherwise hold the
# character in an antic that never finishes.
ANTIC_WALK_SECONDS = 8.0

# The gap between two of them, drawn uniformly — the same shape as the
# companion's own IDLE_MIN/IDLE_MAX, which is this repository's idiom for
# "how long until it does something again".
#
# The floor is SLEEP_AFTER = 45.0, the measured point at which the companion
# declares a settled, untouched character to have nothing to do. Sooner than
# that and the antic lands inside an ordinary stroll: the wander picks a new
# target every 4 to 14 seconds.
#
# The ceiling is a little over three times the floor, a spread close to
# IDLE_MAX/IDLE_MIN (3.5x), so the fidget is as unpredictable as the wandering
# it sits on top of. The mean gap is 97.5 s, which is around thirty-seven
# antics in an hour of an untouched desktop against a hard ceiling of
# BORED_PER_HOUR = 2 spoken remarks in the same hour. Movement outnumbering
# speech eighteen to one is the whole point: the cheap thing is what fills the
# gaps, and the expensive thing stays rare.
ANTIC_MIN, ANTIC_MAX = 45.0, 150.0

# How many of the last picks are off the table. Two, out of a catalogue of
# five: enough that the same fidget cannot appear twice running, and not so
# many that the order stops being random and becomes a rota.
ANTIC_RECENT = 2

Antic = namedtuple("Antic", "name clip seconds moves")

# The catalogue. `clip` names a clip from buddy_sprites and the companion
# resolves it through clip_or_fallback, so one the sheet has not got costs the
# antic and nothing else. `moves` is the difference between a pose and a
# route: the companion picks where, this picks whether.
#
# Every clip in the sheet already means something in _animate, so each of
# these is a clip whose existing meaning either is the antic or cannot be on
# screen at the same time as it:
#
#   walk   is what moving looks like anyway; the antic here is the route, not
#          the pose.
#   peek   is what a docked character does against an edge. The antic is the
#          same act performed on purpose by one that is not docked.
#   yawn   is the one-shot on the way into sleep, which only a docked
#          character reaches. Standing in the open it is a stretch.
#   turn   is the one-shot the companion already replays whenever the facing
#          changes, so a deliberate look behind costs nothing new.
#   point  is insistence rung 4, which needs the pointer opt-in and ten
#          minutes of a session waiting on a human. An antic never starts
#          while a session wants a human, so the two cannot be on screen in
#          the same circumstances — the non-collision is by construction
#          rather than by luck.
#
# Deliberately not in here: `wave` (insistence rung 3), `nod` and `shake` (the
# greeting to another companion), `sit` (a focus block), `type` (something is
# running), `alert` (a session wants the human), `celebrate` (allQuiet, and a
# basket scored), `panic` (the band where the work is about to stop being
# possible), `furious`/`held`/`annoyed`/`land` (a hand on it), `sleep`, and
# `read` — that last one is the book, whose frequency is the --memes setting,
# and an antic that produced it would hand a prop to somebody who set that
# setting to "plain sprite, no props".
ANTICS = (
    Antic("pace", "walk", ANTIC_WALK_SECONDS, True),
    Antic("edge", "peek", ANTIC_WALK_SECONDS, True),
    Antic("doze", "yawn", ANTIC_POSE_SECONDS, False),
    Antic("glance", "turn", ANTIC_POSE_SECONDS, False),
    Antic("poke", "point", ANTIC_POSE_SECONDS, False),
)


def wants_human(sessions):
    """Whether anything on the desktop is blocked on a person right now.

    The states are buddy_focus's rather than a list written again here. Two
    lists of what counts as urgent drift apart, and the one that drifts is the
    one nobody is looking at — the companion says so about its own typing gate
    and it is true here too.
    """
    for row in sessions or ():
        if isinstance(row, dict) and row.get("state") in buddy_focus.WANTS_HUMAN:
            return True
    return False


class Antics:
    """Which fidget, and when. Not what it looks like.

    Driven from the frame path rather than the poll: an antic lasts two to
    eight seconds and the poll is twenty, so a poll-driven one would be over
    before anything read it.

    The failure this is built around is an antic that interrupts something
    that matters. Walking in circles while a session sits on a question is
    noise on top of the one signal the companion exists to carry, so `waiting`
    does not merely block the next antic: it ends the one in flight.
    """

    def __init__(self, enabled=True, catalogue=ANTICS,
                 gap=(ANTIC_MIN, ANTIC_MAX)):
        self.enabled = bool(enabled)
        self.catalogue = tuple(catalogue)
        self.gap = (float(gap[0]), float(gap[1]))
        self._antic = None
        self._ends_at = 0.0
        # None until the first update, for the same reason Boredom's clock is:
        # from zero, `now >= next_at` is true on the first frame and the
        # character starts fidgeting the instant it appears.
        self._next_at = None
        self._recent = []

    def current(self, now):
        """The antic in flight at `now`, or None. A read, and only a read."""
        if self._antic is None or float(now) >= self._ends_at:
            return None
        return self._antic

    def interrupt(self, now=None):
        """End the antic. Anything that matters has started happening.

        `now` pushes the next one out by the floor of the gap, so the fidget
        does not resume the instant a hand comes off it. Without a time there
        is nothing to push against and only the current antic ends.
        """
        self._antic = None
        self._ends_at = 0.0
        if now is not None and self._next_at is not None:
            self._next_at = max(self._next_at, float(now) + self.gap[0])

    def update(self, now, waiting=False, ready=True, rng=random):
        """One call per frame. The antic that just started, or None.

        None on every frame but the one an antic begins on, so a caller can
        hang a one-shot off the return value without replaying it thirty times
        a second. What is on screen right now is `current`.

        `waiting` is wants_human() over the sessions the companion is looking
        at. `ready` is everything else that means the character is not
        available to fidget — being dragged, flying, docked, mid-getaway, in a
        focus block, in an encounter with another companion, or already
        walking somewhere it chose. Both are the caller's readings; only their
        consequences are decided here.
        """
        now = float(now)
        if self._next_at is None:
            self._next_at = now + self._gap(rng)
            return None
        if waiting or not ready or not self.enabled:
            self.interrupt(now)
            return None
        if self._antic is not None:
            if now < self._ends_at:
                return None
            self._antic = None
            self._next_at = now + self._gap(rng)
            return None
        if now < self._next_at:
            return None
        antic = self._choose(rng)
        self._antic = antic
        self._ends_at = now + antic.seconds
        return antic

    # -- internals --

    def _gap(self, rng):
        low, high = self.gap
        return low if high <= low else rng.uniform(low, high)

    def _choose(self, rng):
        fresh = [a for a in self.catalogue if a.name not in self._recent]
        antic = rng.choice(fresh or list(self.catalogue))
        self._recent.append(antic.name)
        del self._recent[:-ANTIC_RECENT]
        return antic


# ── the basket, remembered between baskets ─────────────────────────────────

# How long a run of baskets stays alive, measured from the last one.
#
# buddy_hoop.THROW_MEMORY, and not a number of this module's own. The temper
# holds a throw against you for ninety seconds; the credit for playing along
# has to be remembered for exactly as long, or the character forgives at one
# speed and congratulates at another. Ninety seconds is also comfortably more
# than a run needs: after a basket is scored the next one costs HOOP_AFTER =
# 6 s of holding plus a flight of under two seconds, so three in a row fit
# inside it with room to spare.
STREAK_MEMORY = buddy_hoop.THROW_MEMORY

# The run that earns a different reaction. Three.
#
# buddy_hoop.FURY_AFTER is 2 — "the first throw is the discovery that the
# character can be thrown, and the second is a decision". A basket scored pays
# the temper off in full, so the first two baskets are at most the two throws
# being settled. The third has nothing left to pay off and is therefore the
# first one that is only the game, which is why it is the first that deserves
# something other than "that settles it".
STREAK_MILESTONE = 3

# The keys the companion looks the wording up under. The first is the one it
# already has; a run only ever adds strings, it never changes the meaning of
# the one that shipped.
SCORE_ONE = "hoopScored"
SCORE_AGAIN = "hoopAgain"
SCORE_STREAK = "hoopStreak"

Basket = namedtuple("Basket", "run key best")


class Streak:
    """Consecutive baskets, and how long consecutive lasts.

    What breaks a run, decided rather than inherited:

      a throw that missed          breaks it. That is what a run of baskets
                                   means, and buddy_hoop already counts the
                                   miss; this is the half that acts on it.
      the basket expiring unthrown does not. The companion already tells the
                                   two apart — `hoopMissed` when somebody
                                   threw, `hoopGone` when nobody did — and
                                   ending a run because the person walked away
                                   turns an offer into an obligation.
      the game being put away      does not, directly. A run whose last basket
                                   is older than STREAK_MEMORY is gone whether
                                   the object survived or not, so there is no
                                   second rule to keep in step with the first.
    """

    def __init__(self, memory=STREAK_MEMORY, milestone=STREAK_MILESTONE):
        self.memory = float(memory)
        self.milestone = int(milestone)
        self.best = 0
        self._run = 0
        self._at = None

    def run(self, now):
        """The run still alive at `now`, expiring it on the way past.

        Pruned on read rather than in a sweep of its own, which is
        buddy_hoop.Temper.count's rule and for the same reason: it happens on
        the only path that reads the number.
        """
        if self._at is None:
            return 0
        if float(now) - self._at > self.memory:
            self._run = 0
            self._at = None
        return self._run

    def scored(self, now):
        """Record a basket. The run it makes, and what to say about it."""
        now = float(now)
        run = self.run(now) + 1
        self._run = run
        self._at = now
        self.best = max(self.best, run)
        return Basket(run=run, key=self._key(run), best=self.best)

    def missed(self):
        """A throw that came to rest without scoring. The run is over."""
        self._run = 0
        self._at = None
        return 0

    def _key(self, run):
        if run >= self.milestone:
            return SCORE_STREAK
        if run > 1:
            return SCORE_AGAIN
        return SCORE_ONE


# ── the easter egg ─────────────────────────────────────────────────────────

# What the companion already reads, checked in usage-buddy-companion.py before
# any of this was chosen. Every one of these is a meaning a new gesture must
# not land on top of:
#
#   left click (moved under 6 px)     _go_to_session: raises the terminal of
#                                     the session that needs a human.
#   right click                       the context menu.
#   drag                              moves it; the drop docks it if it lands
#                                     within SNAP_MARGIN = 26 px of an edge.
#   drag held over 3.5 s              DRAG_PATIENCE: "Put me down."
#   drag held 6 s                     HOOP_AFTER: the basket is offered.
#   drag held 5 s, or 900 px of
#     travel, or the second drag
#     inside 90 s                     the getaway, behind TUG_COOLDOWN.
#   drag held 10 s                    DRAG_TUG_ALWAYS: the getaway, no
#                                     cooldown and no forgiveness.
#   release above 90 px/s             a throw; twice inside 90 s and it comes
#                                     for the pointer.
#   a folder dropped on it            a question about that repository.
#
# So: every multi-click sequence is spoken for — each click is another visit to
# a session — and every multi-drag sequence is spoken for too, because the
# second drag inside ninety seconds is already the getaway. What is left is
# one drag, short, and something about its *path*, which nothing reads at all:
# the companion measures a drag's duration, its Manhattan length and the
# velocity of its last ninety milliseconds, and never its shape.
#
# Hence: shake it. One drag, back and forth, over before any of the durations
# above mean anything, shorter than the distance that means something, and let
# go of at rest so the release is a placement rather than a throw. The
# refusals below are what keep that true — the egg declines every drag that
# already means something else, so a release can never be both.

# How many direction changes. Four, which is five legs: the widget's own egg
# needs five taps, so the two eggs on this desktop cost the same number of
# deliberate motions.
EGG_REVERSALS = 4

# The whole gesture's budget, from the moment the drag begins. Half a second
# inside DRAG_PATIENCE (3.5 s), so a shake that only just makes it is still
# over before the character starts complaining about being held — and well
# inside DRAG_TUG_SECONDS (5 s) and HOOP_AFTER (6 s), which are the next two
# things a held drag turns into.
EGG_SECONDS = 3.0

# ...divided by the five legs it has to hold, which is what "how long it
# tolerates between steps" means here. A reversal that arrives later than this
# is not a slow shake, it is somebody moving the character about; the count
# starts again from that reversal rather than being abandoned, so a hand that
# hesitates once and then shakes properly still gets its egg.
EGG_STEP_SECONDS = EGG_SECONDS / (EGG_REVERSALS + 1)

# How far a leg has to run before the turn at the end of it counts. The
# companion ignores movement under 6 px as "a click with a shaky hand"; four
# times that is unambiguously a stroke of the arm, and it is still under half
# the sprite's own width (BUDDY_PX = 56), so the shake stays a shake rather
# than becoming a journey.
EGG_MIN_LEG = 24.0

# The distance at which a drag already means something. DRAG_TUG_DISTANCE,
# restated: at or past it the companion runs off with the pointer, and a
# release must never be both that and an egg. Five legs under this leaves
# 180 px a leg, which is seven times EGG_MIN_LEG.
EGG_MAX_TRAVEL = 900.0

# How long the egg ignores further shakes once it has fired. The widget's egg
# gives itself thirty seconds before it forgets it was triggered
# (eggTimeout: 30000 in main.qml); the same number here means the two eggs on
# this desktop behave alike, and it is what stops a shake from being a way to
# be picked up repeatedly without the companion ever reacting to the drags.
EGG_COOLDOWN = 30.0

# What each shake advances to. Three: two would read as a toggle rather than a
# cycle, and the reaction to each is the companion's — this end only says
# which one is now due, and cycles so the fourth shake is the first again
# instead of running out.
EGG_STEPS = ("dizzy", "delighted", "sulking")

EggStep = namedtuple("EggStep", "index name")


class Egg:
    """Shaking the character, recognised. The reaction is not this module's.

    A state machine one drag wide. `grabbed` opens it, `moved` feeds it the
    hand's positions, and `released` is the only place it ever answers — a
    gesture that has not been let go of is not yet a gesture.

    Reversals are counted on the horizontal axis alone. Both axes would count
    a circle as four reversals, and drawing a circle with a mascot in your
    hand is not a thing anybody means; left and right is also the axis the
    character itself lives on, since facing, walking and the getaway are all
    horizontal.
    """

    def __init__(self, enabled=True, steps=EGG_STEPS):
        self.enabled = bool(enabled)
        self.steps = tuple(steps)
        self._started = None     # when the drag this is reading began
        self._anchor = None      # x at the first sample
        self._extreme = None     # furthest x in the current direction
        self._sign = 0           # +1 right, -1 left, 0 not established
        self._turned_at = 0.0
        self._reversals = 0
        self._fired_at = None
        self._step = -1          # so the first egg is steps[0]

    @property
    def reversals(self):
        """Direction changes counted in the drag being read. Diagnostic."""
        return self._reversals

    def forget(self):
        """Drop the gesture being read. Nothing about the cycle is lost."""
        self._started = None
        self._anchor = None
        self._extreme = None
        self._sign = 0
        self._turned_at = 0.0
        self._reversals = 0

    def grabbed(self, now):
        """A drag has begun. Everything before it is not part of this one."""
        self.forget()
        self._started = float(now)
        self._turned_at = float(now)

    def moved(self, now, position):
        """One sample of where the hand is, in the companion's own pixels.

        `position` is (x, y) — buddy_hoop's convention for a pointer reading —
        and y is not read. Samples arriving with no `grabbed` in front of them
        are ignored rather than treated as the start of a drag: a stream that
        begins in the middle has no start time, and without one the budget
        that keeps this from colliding with DRAG_PATIENCE cannot be applied.
        """
        if self._started is None:
            return
        try:
            x = float(position[0])
        except (TypeError, ValueError, IndexError, KeyError):
            return
        now = float(now)
        if self._anchor is None:
            self._anchor = self._extreme = x
            return
        if self._sign == 0:
            # The first leg. Nothing has turned around yet, so there is
            # nothing to time; a stroke shorter than EGG_MIN_LEG is jitter.
            if abs(x - self._anchor) >= EGG_MIN_LEG:
                self._sign = 1 if x > self._anchor else -1
                self._extreme = x
                self._turned_at = now
            return
        if (x - self._extreme) * self._sign > 0:
            self._extreme = x       # still going the same way
            return
        if abs(x - self._extreme) < EGG_MIN_LEG:
            return                  # a wobble at the end of a stroke
        if now - self._turned_at > EGG_STEP_SECONDS:
            # Too slow to be part of the same shake. This turn is the first of
            # a new attempt rather than the fifth of a failed one.
            self._reversals = 0
        self._reversals += 1
        self._turned_at = now
        self._sign = -self._sign
        self._extreme = x

    def released(self, now, thrown=False, travelled=0.0):
        """The verdict on the drag that just ended: an EggStep, or None.

        Every refusal here is a collision being avoided rather than a fussy
        rule. `thrown` is the companion's own reading of the release — above
        buddy_actions.THROW_MIN_SPEED it is a throw, the temper counts it and
        two of them bring the getaway, so a release cannot also be an egg.
        `travelled` is the drag's Manhattan length, which at EGG_MAX_TRAVEL is
        already the getaway. The budget refuses a drag long enough to have
        earned "Put me down", and the cooldown refuses a second egg close
        enough behind the first to be the same gesture read twice.

        The gesture is dropped on the way out either way, so a release is
        never read twice and a refused shake does not leave four reversals
        lying around for the next drag to inherit.
        """
        try:
            step = self._verdict(float(now), thrown, travelled)
        finally:
            self.forget()
        return step

    # -- internals --

    def _verdict(self, now, thrown, travelled):
        if not self.enabled or self._started is None:
            return None
        if thrown:
            return None
        try:
            distance = float(travelled)
        except (TypeError, ValueError):
            return None
        if distance >= EGG_MAX_TRAVEL:
            return None
        if now - self._started > EGG_SECONDS:
            return None
        if self._reversals < EGG_REVERSALS:
            return None
        if self._fired_at is not None and now - self._fired_at < EGG_COOLDOWN:
            return None
        self._fired_at = now
        self._step = (self._step + 1) % len(self.steps)
        return EggStep(index=self._step, name=self.steps[self._step])
