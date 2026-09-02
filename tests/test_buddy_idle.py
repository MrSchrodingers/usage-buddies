"""Boredom, antics, the streak and the easter egg, and the ways each goes bad.

The four here fail in four different directions and only one of them is loud.

Boredom becomes Clippy: a mascot that opens its mouth with nothing to report
is the thing this project was built not to be, so the failure is not an
exception, it is the program turning into the program it was written against.
Antics become noise: silent movement is cheap right up to the moment it walks
in circles while a session sits on a question, and then it is competing with
the one signal the companion exists to carry. The streak becomes a liar: a run
that survives a miss, or one that dies because nobody threw, congratulates the
wrong thing. And the egg becomes ambiguous: a gesture that is also a throw, or
also the getaway, means one release did two things and neither of them
clearly.

Time is an argument throughout and so is the random, so none of this sleeps
and none of it flakes.
"""
import sys
from itertools import pairwise
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import buddy_focus
import buddy_hoop
import buddy_idle as idle

# POLL_MS in usage-buddy-companion.py, in seconds. The cadence every decision
# in this module is actually offered at, so a rarity measured on any other
# step is a rarity nobody will experience.
POLL_SECONDS = 20.0

# DRAG_PATIENCE and DRAG_TUG_DISTANCE, restated from the companion, so the
# collision tests are written against the numbers that are really in force
# rather than against buddy_idle's copies of them.
DRAG_PATIENCE = 3.5
DRAG_TUG_DISTANCE = 900


class _Always:
    """A random that always fires and always takes the low end of a range.

    The point of pinning it this way is that every ceiling below has to hold
    when the coin never once comes up against it. A rarity that depends on
    luck is a rarity that can fail for a whole afternoon.
    """

    @staticmethod
    def random():
        return 0.0

    @staticmethod
    def uniform(low, _high):
        return low

    @staticmethod
    def choice(seq):
        return next(iter(seq))


class _Never:
    """A random that never fires."""

    @staticmethod
    def random():
        return 1.0

    @staticmethod
    def uniform(_low, high):
        return high

    @staticmethod
    def choice(seq):
        return list(seq)[-1]


def _polls(start, span, step=POLL_SECONDS):
    """The moments the companion would actually ask, over `span` seconds."""
    now = float(start)
    stop = float(start) + float(span)
    while now < stop:
        yield now
        now += step


def _session(pid=1, state="asking"):
    return {"pid": pid, "state": state, "name": "hub", "idleSeconds": 0}


# ── boredom ────────────────────────────────────────────────────────────────

def test_boredom_says_nothing_during_a_focus_block_or_the_moment_after_one():
    """A block is silence somebody asked for, and the failure has two halves.

    The obvious one is talking during it. The one that only shows up in the
    running program is talking the instant it ends: the block is longer than
    BORED_AFTER, so a clock that merely paused while it ran comes out the far
    side already overdue and spends the block's own silence on a remark. The
    block ending is the character's cue to walk back and say the block is
    over, not to say something about nothing.
    """
    bored = idle.Boredom(enabled=True)
    bored.due(0.0, rng=_Always())
    block = buddy_focus.FocusSession().start(0.0, minutes=25)
    last = 0.0
    for now in _polls(0.0, 1500.0):
        assert not bored.due(now, silenced=block.silences(now), rng=_Always()), now
        last = now
    # The block has run out. Nothing is silencing it any more, and it still
    # has to wait out a real silence of its own, counted from the last poll of
    # the block rather than from the start of the block.
    assert not bored.due(1500.0, rng=_Always()), "cashed the block in for a remark"
    assert not bored.due(last + idle.BORED_AFTER - 1.0, rng=_Always())
    assert bored.due(last + idle.BORED_AFTER, rng=_Always())


def test_boredom_does_not_talk_over_a_line_that_has_a_reason():
    """A measured line is going out this poll: something did happen, so there
    is nothing to be bored about. Two lines in one poll is also two bubbles,
    and the second replaces the first — the one with a reason behind it."""
    bored = idle.Boredom(enabled=True)
    bored.due(0.0, rng=_Always())
    for now in _polls(0.0, 3600.0):
        assert not bored.due(now, trigger=True, rng=_Always()), now


def test_boredom_stays_under_its_declared_ceiling_over_an_hour():
    """The number the whole thing exists to defend.

    An untouched desktop, asked at the rate it is really asked at, with a coin
    that comes up in favour every single time — so what is measured here is
    the structure and not the luck. Past the ceiling and this is a mascot that
    puts a sentence on screen every couple of minutes, which is the failure
    the project was built against.
    """
    bored = idle.Boredom(enabled=True)
    coin = _Always()
    bored.due(0.0, rng=coin)
    said = [now for now in _polls(0.0, 3600.0) if bored.due(now, rng=coin)]
    assert len(said) <= idle.BORED_PER_HOUR, said
    gaps = [b - a for a, b in pairwise(said)]
    assert all(gap >= idle.BORED_GAP for gap in gaps), gaps


def test_boredom_switched_off_never_speaks_however_long_it_waits():
    """The off switch is the whole reason this may exist at all. A day of an
    untouched desktop is the longest anybody will leave one running without
    noticing, and it has to buy exactly nothing."""
    bored = idle.Boredom(enabled=False)
    bored.due(0.0, rng=_Always())
    for now in _polls(0.0, 24 * 3600.0):
        assert not bored.due(now, rng=_Always()), now


def test_boredom_is_off_unless_somebody_asked_for_it():
    """The default is the whole of the compatibility story: an upgrade must
    not turn the mode the README recommends into a chatty one."""
    assert idle.BORED_DEFAULT is False
    bored = idle.Boredom()
    bored.due(0.0, rng=_Always())
    assert not bored.due(10_000.0, rng=_Always())


def test_boredom_waits_out_a_real_silence_before_the_first_word():
    """Ten minutes of nothing, and it is the collector's ten minutes rather
    than a number of its own. Below it, something did happen recently and the
    remark is an interruption rather than company."""
    bored = idle.Boredom(enabled=True)
    bored.happened(0.0)
    for now in _polls(0.0, idle.BORED_AFTER):
        assert not bored.due(now, rng=_Always()), now
    assert bored.due(idle.BORED_AFTER, rng=_Always())


def test_anything_that_happened_starts_the_silence_over():
    """Boredom is measured from the last thing that happened, not from the
    last poll. A hand on the character nine minutes in and it starts again;
    otherwise the remark lands a minute after somebody put it down.

    The clock is opened by a poll rather than by `happened`, so a `happened`
    that quietly does nothing cannot hide behind the first-call case.
    """
    bored = idle.Boredom(enabled=True)
    bored.due(0.0, rng=_Always())
    bored.happened(idle.BORED_AFTER - 60.0)
    assert not bored.due(idle.BORED_AFTER, rng=_Always()), "spoke a minute after a touch"
    assert bored.due(idle.BORED_AFTER * 2 - 60.0, rng=_Always())


def test_a_granted_remark_is_recorded_by_the_call_that_granted_it():
    """`due` is a read that writes, on purpose. Turned into a plain predicate
    with the acknowledgement split off, a caller is free to forget the second
    half, and one that forgets it gets a character that speaks on every poll
    for the rest of the session — the exact failure this class exists to make
    impossible. Asking twice in the same poll is how that refactor shows.
    """
    bored = idle.Boredom(enabled=True)
    bored.happened(0.0)
    assert bored.due(idle.BORED_AFTER, rng=_Always())
    assert not bored.due(idle.BORED_AFTER, rng=_Always()), "granted twice in one poll"
    assert not bored.due(idle.BORED_AFTER + 1.0, rng=_Always())


def test_the_roll_is_consulted_so_the_remark_is_not_a_metronome():
    """A remark that arrives at exactly the same second of every half hour is
    a cron job with a face, and it is the shape people notice and then resent.
    The coin is also the reason the ceiling above is enforced by the gap: a
    rarity that depends on the coin is a rarity that can come up heads."""
    bored = idle.Boredom(enabled=True)
    bored.happened(0.0)
    for now in _polls(0.0, 3600.0):
        assert not bored.due(now, rng=_Never()), now


def test_the_boredom_clock_starts_when_it_is_first_asked():
    """`now` is a monotonic clock, which on a machine that has been up for a
    week is a number in the hundreds of thousands. A clock initialised to zero
    makes a companion three seconds old already overdue, and the first thing
    it does on screen is talk to itself."""
    uptime = 604_800.0
    bored = idle.Boredom(enabled=True)
    assert not bored.due(uptime, rng=_Always()), "bored before it had existed a frame"
    assert bored.waited == uptime


# ── antics ─────────────────────────────────────────────────────────────────

def test_no_antic_starts_while_a_session_is_waiting_for_a_person():
    """The declared failure: walking in circles while something waits on a
    human is noise laid over the one signal the companion exists to carry."""
    antics = idle.Antics()
    antics.update(0.0, rng=_Always())
    for now in _polls(0.0, 1800.0):
        started = antics.update(now, waiting=True, rng=_Always())
        assert started is None, (now, started)
        assert antics.current(now) is None


def test_an_antic_already_running_is_cut_short_when_a_session_starts_waiting():
    """Refusing to start a new one is the easy half. An antic is seconds long
    and a session can start waiting inside those seconds; left to finish, the
    character strolls off exactly as the thing it should react to appears."""
    antics = idle.Antics()
    antics.update(0.0, rng=_Always())
    started = antics.update(idle.ANTIC_MIN, rng=_Always())
    assert started is not None
    mid = idle.ANTIC_MIN + started.seconds / 2.0
    assert antics.current(mid) is not None
    antics.update(mid, waiting=True, rng=_Always())
    assert antics.current(mid) is None, "kept fidgeting while a session waited"


def test_an_antic_does_not_start_on_the_first_frame():
    """The frame timer starts before anything else does. A gap counted from
    zero is already elapsed against a monotonic clock, so the character's
    first act on screen is a fidget rather than arriving."""
    antics = idle.Antics()
    assert antics.update(604_800.0, rng=_Always()) is None
    assert antics.current(604_800.0) is None


def test_an_antic_ends_on_its_own_and_the_next_one_waits_out_the_gap():
    """Two failures at once. An antic with no end holds the pose for good, and
    one whose end is also the next one's start makes the character fidget
    without pause, which is a twitch rather than a life."""
    antics = idle.Antics()
    antics.update(0.0, rng=_Always())
    started = antics.update(idle.ANTIC_MIN, rng=_Always())
    ended = idle.ANTIC_MIN + started.seconds
    assert antics.current(ended - 0.01) is not None
    antics.update(ended, rng=_Always())
    assert antics.current(ended) is None, "the pose never let go"
    assert antics.update(ended + idle.ANTIC_MIN - 0.01, rng=_Always()) is None
    assert antics.update(ended + idle.ANTIC_MIN, rng=_Always()) is not None


def test_only_one_antic_is_ever_in_flight():
    """A second one starting over the first leaves two clips claiming the
    sprite, and which one wins depends on the order of two ifs."""
    antics = idle.Antics()
    antics.update(0.0, rng=_Always())
    first = antics.update(idle.ANTIC_MIN, rng=_Always())
    assert first is not None
    for now in _polls(idle.ANTIC_MIN, first.seconds, step=0.033):
        assert antics.update(now, rng=_Always()) is None, now


def test_the_same_antic_does_not_come_up_twice_running():
    """Out of five, an unweighted draw repeats one in five times, and a
    character that pokes the edge twice in a row reads as stuck rather than
    as idle.

    The draw here is pinned to the first option every time, which is what a
    catalogue with no memory would hand back over and over — so what this
    measures is the memory and not the shuffle.
    """
    antics = idle.Antics()
    rng = _Always()
    antics.update(0.0, rng=rng)
    now = 0.0
    seen = []
    for _ in range(8):
        now += idle.ANTIC_MIN
        started = antics.update(now, rng=rng)
        assert started is not None, now
        seen.append(started.name)
        now += started.seconds
        antics.update(now, rng=rng)
    assert all(a != b for a, b in pairwise(seen)), seen


def test_no_antic_claims_a_pose_that_already_means_something_else():
    """Every clip in the sheet already has a meaning in the companion's
    _animate. An antic that borrows one of the loud ones makes the character
    celebrate, panic or wave somebody over with nothing behind it, which is
    worse than not fidgeting at all — the poses that mean something are the
    ones people learn to read.

    `point` is deliberately absent from this list: it is insistence rung 4,
    which needs a session that has wanted a human for ten minutes, and no
    antic ever starts while a session wants a human.
    """
    spoken_for = {"wave", "nod", "shake", "sit", "type", "alert", "celebrate",
                  "panic", "furious", "held", "annoyed", "land", "sleep",
                  "read", "talk"}
    borrowed = sorted({a.clip for a in idle.ANTICS} & spoken_for)
    assert borrowed == [], borrowed


def test_an_antic_never_outlasts_the_gap_that_follows_it():
    """An antic longer than the shortest gap would still be running when the
    next one is due, and the rhythm collapses into a single continuous
    performance."""
    for antic in idle.ANTICS:
        assert antic.seconds < idle.ANTIC_MIN, antic


def test_a_session_that_is_merely_busy_does_not_hold_the_antics_back():
    """The gate is a session blocked on a person, not a session at all. Read
    too broadly it silences the fidget on any desktop with work running, which
    is every desktop this ships to."""
    assert idle.wants_human([_session(1, "asking")])
    assert idle.wants_human([_session(1, "working"), _session(2, "waiting")])
    assert not idle.wants_human([_session(1, "working"), _session(2, "idle")])
    assert not idle.wants_human([_session(1, "background")])
    assert not idle.wants_human([])
    assert not idle.wants_human(None)


def test_the_waiting_gate_reads_the_states_buddy_focus_declares():
    """Two lists of what counts as urgent drift apart, and the one that drifts
    is the one nobody is looking at."""
    for state in buddy_focus.WANTS_HUMAN:
        assert idle.wants_human([_session(1, state)]), state


# ── the streak ─────────────────────────────────────────────────────────────

def test_a_throw_that_missed_ends_the_run():
    """The one thing that breaks it, and the plain meaning of a run of
    baskets. A streak that survives a miss is congratulating somebody for
    having thrown at all."""
    streak = idle.Streak()
    assert streak.scored(0.0).run == 1
    assert streak.scored(10.0).run == 2
    streak.missed()
    assert streak.run(11.0) == 0
    assert streak.scored(12.0).run == 1, "the miss did not break it"


def test_a_basket_nobody_threw_at_does_not_end_the_run():
    """The companion already tells the two apart — `hoopMissed` when somebody
    threw, `hoopGone` when nobody did. Ending a run because the person walked
    away turns the offer into an obligation, and the offer is the whole
    point of the game."""
    streak = idle.Streak()
    streak.scored(0.0)
    streak.scored(10.0)
    # The basket went up and expired: buddy_hoop.clear(), no miss recorded.
    assert streak.run(20.0) == 2, "walking away was counted as failing"
    assert streak.scored(30.0).run == 3


def test_a_run_does_not_outlive_the_temper_that_it_pays_off():
    """A run held forever means coming back an hour later and being told this
    is the fourth in a row. It is not: it is the first of a new game, and the
    temper that the game exists to settle has itself forgotten by then."""
    streak = idle.Streak()
    streak.scored(0.0)
    streak.scored(10.0)
    assert streak.run(10.0 + idle.STREAK_MEMORY) == 2
    assert streak.run(10.0 + idle.STREAK_MEMORY + 0.01) == 0
    assert streak.scored(10.0 + idle.STREAK_MEMORY + 1.0).run == 1


def test_the_run_is_forgotten_on_exactly_the_temper_s_own_window():
    """Forgiving at one speed and congratulating at another gives a character
    that is still angry about a throw it has already been paid for."""
    assert idle.STREAK_MEMORY == buddy_hoop.THROW_MEMORY


def test_the_third_basket_in_a_row_is_not_reported_like_the_first():
    """The whole of the ask. One basket settles a throw; three in a row is a
    person playing the game, and saying "that settles it" three times running
    is a character that did not notice."""
    streak = idle.Streak()
    assert streak.scored(0.0).key == idle.SCORE_ONE
    assert streak.scored(5.0).key == idle.SCORE_AGAIN
    third = streak.scored(10.0)
    assert third.key == idle.SCORE_STREAK
    assert third.run == idle.STREAK_MILESTONE
    assert streak.scored(15.0).key == idle.SCORE_STREAK


def test_a_run_that_was_broken_is_reported_from_the_beginning_again():
    """The counter and the wording have to break together. Reset one and not
    the other and the next single basket arrives announced as a streak."""
    streak = idle.Streak()
    streak.scored(0.0)
    streak.scored(5.0)
    streak.scored(10.0)
    streak.missed()
    fresh = streak.scored(11.0)
    assert (fresh.run, fresh.key) == (1, idle.SCORE_ONE)
    assert fresh.best == 3, "the best run was thrown away with the current one"


# ── the easter egg ─────────────────────────────────────────────────────────

def _stroke(egg, now, x, direction, amplitude=60.0, seconds=0.2, steps=3):
    """One leg of a shake, as the mouse would deliver it. Returns (now, x)."""
    for _ in range(steps):
        now += seconds / steps
        x += direction * amplitude / steps
        egg.moved(now, (x, 500.0))
    return now, x


def _shake(egg, start, legs=5, x0=1000.0, **kw):
    """A whole shake, from the grab to the last sample. Returns the time."""
    egg.grabbed(start)
    now, x = start, x0
    egg.moved(now, (x, 500.0))
    direction = 1
    for _ in range(legs):
        now, x = _stroke(egg, now, x, direction, **kw)
        direction = -direction
    return now


def test_the_gestures_the_companion_already_reads_do_not_hatch_the_egg():
    """The failure that makes an easter egg a bug: one release meaning two
    things. Every sequence here is one the companion already interprets, taken
    from mousePressEvent, mouseMoveEvent and mouseReleaseEvent, and none of
    them may come back with an egg.
    """
    # A click. It never becomes a drag at all — the companion ignores movement
    # under 6 px — and a click is already a visit to the session that needs a
    # human.
    egg = idle.Egg()
    egg.grabbed(0.0)
    assert egg.released(0.05) is None, "a click hatched it"

    # A release with no drag in front of it at all.
    assert idle.Egg().released(0.0) is None

    # Putting it down somewhere: one stroke, released at rest.
    egg = idle.Egg()
    egg.grabbed(0.0)
    now, _x = _stroke(egg, 0.0, 1000.0, 1, amplitude=300.0, seconds=1.0, steps=10)
    assert egg.released(now, travelled=300.0) is None, "a placement hatched it"

    # Out and back once. Two strokes is not a shake, and it is the shape of
    # picking the character up and changing your mind.
    egg = idle.Egg()
    assert egg.released(_shake(egg, 0.0, legs=2), travelled=120.0) is None

    # Hauling it across the desktop: DRAG_TUG_DISTANCE is already the getaway.
    egg = idle.Egg()
    now = _shake(egg, 0.0, amplitude=DRAG_TUG_DISTANCE / 4.0)
    assert egg.released(now, travelled=DRAG_TUG_DISTANCE) is None, "and the getaway too"

    # Holding on past the point where the character starts complaining.
    egg = idle.Egg()
    now = _shake(egg, 0.0)
    assert egg.released(now + DRAG_PATIENCE, travelled=300.0) is None, "past patience"

    # Throwing it. Above THROW_MIN_SPEED the release is a throw, the temper
    # counts it, and two of them bring the getaway.
    egg = idle.Egg()
    now = _shake(egg, 0.0)
    assert egg.released(now, thrown=True, travelled=300.0) is None, "a throw hatched it"


def test_a_shake_hatches_it():
    """The other half: a guard that refuses everything passes every test above
    and ships an easter egg nobody can reach."""
    egg = idle.Egg()
    now = _shake(egg, 0.0)
    assert egg.reversals == idle.EGG_REVERSALS
    step = egg.released(now, travelled=300.0)
    assert step is not None, "the gesture it was built for did nothing"
    assert step.name == idle.EGG_STEPS[0]


def test_a_shake_that_stalls_between_strokes_is_not_one_gesture():
    """A hand that moves the character left, thinks, then moves it right is
    not shaking it — it is deciding where to put it. Counting across the pause
    turns a slow placement into an easter egg.

    Every stroke here is slower than the tolerance and the whole drag is still
    inside the budget, so the refusal below can only be about the count.
    """
    egg = idle.Egg()
    egg.grabbed(0.0)
    now, x = 0.0, 1000.0
    egg.moved(now, (x, 500.0))
    now, x = _stroke(egg, now, x, 1, seconds=0.06)
    for direction in (-1, 1, -1, 1):
        now += idle.EGG_STEP_SECONDS + 0.02      # the hand stops to think
        now, x = _stroke(egg, now, x, direction, seconds=0.06)
    # Five strokes and four turns: enough that a count which ignored the
    # pauses would reach EGG_REVERSALS, and still inside the budget, so the
    # refusal below can only be about the pauses.
    assert now < idle.EGG_SECONDS, now
    assert egg.reversals < idle.EGG_REVERSALS, egg.reversals
    assert egg.released(now, travelled=300.0) is None


def test_a_hand_that_hesitates_once_and_then_shakes_still_gets_its_egg():
    """The pause resets the count, it does not poison the drag. Otherwise a
    single moment of hesitation makes the gesture unreachable until the person
    lets go and starts again, which reads as the egg being broken."""
    egg = idle.Egg()
    egg.grabbed(0.0)
    now, x = 0.0, 1000.0
    egg.moved(now, (x, 500.0))
    now, x = _stroke(egg, now, x, 1)
    now, x = _stroke(egg, now, x, -1, seconds=idle.EGG_STEP_SECONDS * 2)
    for direction in (1, -1, 1):
        now, x = _stroke(egg, now, x, direction)
    assert now < idle.EGG_SECONDS, now
    assert egg.reversals >= idle.EGG_REVERSALS, egg.reversals
    assert egg.released(now, travelled=300.0) is not None


def test_a_wobble_inside_one_stroke_is_not_a_direction_change():
    """A hand does not travel in a straight line. Counting every sample whose
    sign differs from the last turns ordinary tremor into four reversals, and
    then every drag on the desktop is an easter egg."""
    egg = idle.Egg()
    egg.grabbed(0.0)
    now, x = 0.0, 1000.0
    egg.moved(now, (x, 500.0))
    for _ in range(12):
        now += 0.02
        x += 40.0
        egg.moved(now, (x, 500.0))
        now += 0.02
        x -= 8.0          # a third of EGG_MIN_LEG: tremor, not a turn
        egg.moved(now, (x, 500.0))
    assert egg.reversals == 0, egg.reversals
    assert egg.released(now, travelled=576.0) is None


def test_the_egg_cycles_instead_of_running_out():
    """An egg with a last step stops being an egg after three shakes, and the
    fourth reads as the feature having broken."""
    egg = idle.Egg()
    now = 0.0
    seen = []
    for _ in range(len(idle.EGG_STEPS) + 2):
        now += idle.EGG_COOLDOWN
        end = _shake(egg, now)
        step = egg.released(end, travelled=300.0)
        assert step is not None, now
        seen.append(step.name)
        now = end
    assert seen[:len(idle.EGG_STEPS)] == list(idle.EGG_STEPS), seen
    assert seen[len(idle.EGG_STEPS)] == idle.EGG_STEPS[0], seen


def test_a_second_shake_inside_the_cooldown_is_not_a_second_egg():
    """Without it, shaking the character is a way of being picked up over and
    over while the companion answers with the egg every time — and the drags
    that would otherwise have provoked it are all consumed."""
    egg = idle.Egg()
    end = _shake(egg, 0.0)
    assert egg.released(end, travelled=300.0) is not None
    again = _shake(egg, end + 1.0)
    assert egg.released(again, travelled=300.0) is None, "hatched twice in a second"
    later = _shake(egg, end + idle.EGG_COOLDOWN)
    assert egg.released(later, travelled=300.0) is not None


def test_a_refused_shake_leaves_nothing_behind_for_the_next_drag():
    """Reversals kept across a release accumulate: two innocent drags in a row
    add up to a gesture neither of them was, and the egg fires on a movement
    nobody made."""
    egg = idle.Egg()
    now = _shake(egg, 0.0)
    assert egg.released(now, thrown=True, travelled=300.0) is None
    assert egg.reversals == 0
    egg.grabbed(now + 1.0)
    end, _x = _stroke(egg, now + 1.0, 1000.0, 1, amplitude=120.0)
    assert egg.released(end, travelled=120.0) is None, "inherited the last drag"


def test_the_egg_can_be_switched_off():
    """Every part of this module inverts the rule the project was built on in
    some direction, so every part of it has an off switch."""
    egg = idle.Egg(enabled=False)
    now = _shake(egg, 0.0)
    assert egg.released(now, travelled=300.0) is None


def test_junk_from_the_input_stack_does_not_reach_the_verdict():
    """These are fed from mouse events on a frame path. A raise inside one is
    the process, not the frame, so a sample that is not a pair of numbers has
    to cost the gesture and nothing else."""
    egg = idle.Egg()
    egg.grabbed(0.0)
    for junk in (None, (), ("x", "y"), 7, {"x": 1}):
        egg.moved(0.1, junk)
    assert egg.reversals == 0
    assert egg.released(0.2, travelled=None) is None


def test_the_shake_budget_stays_clear_of_everything_it_could_collide_with():
    """The budget is the only thing keeping the gesture out of DRAG_PATIENCE,
    DRAG_TUG_SECONDS and HOOP_AFTER, and the travel ceiling is the only thing
    keeping it out of the getaway. Widened past the first of them the egg and
    "Put me down" fire on the same release; widened past the second, the egg
    and the run at the pointer do."""
    assert idle.EGG_SECONDS < DRAG_PATIENCE
    assert idle.EGG_MAX_TRAVEL <= DRAG_TUG_DISTANCE
    assert idle.EGG_STEP_SECONDS * (idle.EGG_REVERSALS + 1) <= idle.EGG_SECONDS
