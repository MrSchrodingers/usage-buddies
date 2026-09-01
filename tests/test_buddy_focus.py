"""Focus mode, and the four ways a well-meaning one goes wrong.

It goes mute — a lock on a pid that never comes back, or quiet hours derived
from a history two hours long, and the companion says nothing again ever and
nobody finds out why. It twitches — an insistence rung computed from a number
that can fall, so the character waves, talks, waves again. It lies — an idle
reading of zero from a probe that failed, which is indistinguishable from the
person typing. And it takes the mouse away, which is the one thing here that
cannot be undone by ignoring it.

Time is an argument throughout, so none of this sleeps.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import buddy_focus as focus


# Measured on the machine this was written for: ~/.claude/widget-data.json,
# lifetime.peakHours. 538 observations across 18 hours, busiest at 14:00.
REAL_PEAK_HOURS = {0: 7, 1: 3, 2: 2, 9: 19, 10: 43, 11: 63, 12: 41, 13: 28,
                   14: 76, 15: 50, 16: 60, 17: 45, 18: 47, 19: 33, 20: 8,
                   21: 7, 22: 4, 23: 2}


def _session(pid=1, state="asking", name="hub"):
    return {"pid": pid, "state": state, "name": name, "idleSeconds": 0}


# ── the block itself ──

def test_a_block_ends_exactly_when_it_was_asked_to():
    """A twenty-five minute block that runs twenty-six, or twenty-four, is a
    timer nobody trusts twice."""
    block = focus.FocusSession().start(1000.0, minutes=25)
    assert block.remaining(1000.0) == 1500.0
    assert not block.expired(1000.0 + 1499.9)
    assert block.expired(1000.0 + 1500.0)
    assert block.remaining(1000.0 + 1500.0) == 0.0
    assert block.remaining(1000.0 + 9999.0) == 0.0, "remaining went negative"


def test_the_fraction_climbs_from_zero_to_one_and_stays_there():
    """Anything drawn from this — a ring, a bar — jumps backwards or overflows
    if the fraction is not monotonic and clamped."""
    block = focus.FocusSession().start(0.0, minutes=10)
    seen = [block.fraction(t) for t in range(0, 900, 15)]
    assert seen[0] == 0.0
    assert seen == sorted(seen), f"the fraction went backwards: {seen}"
    assert block.fraction(600.0) == 1.0
    assert block.fraction(5000.0) == 1.0, "ran past the end of its own block"


def test_a_block_that_was_never_started_is_not_a_finished_one():
    """`idle` and `done` look identical to a clock and mean opposite things to
    the character. Folded together, the companion announces the end of a block
    nobody asked for, once per poll."""
    block = focus.FocusSession()
    assert block.phase(0.0) == focus.PHASE_IDLE
    assert block.fraction(0.0) == 0.0
    assert not block.expired(1e9)


def test_the_last_minute_is_its_own_phase():
    """Flipping straight from running to done gives a dozing companion no
    frames to walk back in: the end reads as a bubble out of nowhere."""
    block = focus.FocusSession().start(0.0, minutes=25)
    assert block.phase(0.0) == focus.PHASE_RUNNING
    assert block.phase(1440.0 - 1) == focus.PHASE_RUNNING
    assert block.phase(1440.0) == focus.PHASE_ENDING
    assert block.phase(1499.0) == focus.PHASE_ENDING
    assert block.phase(1500.0) == focus.PHASE_DONE


def test_a_block_swallows_the_joke_and_lets_the_question_through():
    """A focus mode that still tells jokes is not a focus mode. A session with
    a question on screen is the exception: it is blocked on a human and stays
    blocked until one turns up."""
    block = focus.FocusSession().start(0.0, minutes=25)
    for key in ("philosophy", "ambient", "cacheDrop", "sessionSpread",
                "background", "waiting", "nightOwl"):
        assert not block.allows(key, 60.0), f"{key} spoke during a focus block"
    assert block.allows("asking", 60.0)


def test_an_expired_block_stops_silencing_before_it_is_acknowledged():
    """There is at least one poll between a block running out and the
    companion noticing. Staying quiet through it delays every alert the block
    was holding, which is the failure the block existed to avoid."""
    block = focus.FocusSession().start(0.0, minutes=25)
    assert not block.allows("philosophy", 1499.0)
    assert block.allows("philosophy", 1500.0)


def test_a_cancelled_block_is_not_reported_as_finished():
    """Giving up on a block is not completing one, and the character has
    nothing to celebrate about it."""
    block = focus.FocusSession().start(0.0, minutes=25)
    block.cancel()
    assert block.phase(600.0) == focus.PHASE_IDLE
    assert block.allows("philosophy"), "still muzzled after being called off"


# ── the escort ──

def test_the_escort_reduces_the_list_to_the_session_it_holds():
    """Rotating between sessions is right for surveillance and wrong for
    someone who has decided to deal with one of them."""
    rows = [_session(1, "asking", "hub"), _session(2, "waiting", "api"),
            _session(3, "asking", "db")]
    escort = focus.Escort()
    escort.lock(2, state="waiting")
    assert escort.locked_on == 2
    assert [s["name"] for s in escort.filter(rows)] == ["api"]


def test_the_escort_lets_go_when_the_session_leaves_that_state():
    """The escort exists to see one thing through. Once it is through there is
    nothing left to escort, and holding on hides the other two sessions."""
    escort = focus.Escort()
    escort.lock(2, state="waiting")
    rows = [_session(1, "asking"), _session(2, "working", "api")]
    assert len(escort.filter(rows)) == 2
    assert escort.locked_on is None


def test_an_escort_holding_a_pid_that_vanished_does_not_mute_the_companion():
    """The failure that has no way out from the user's side: a lock on a dead
    pid filters every list down to nothing, forever, with no visible cause."""
    escort = focus.Escort()
    escort.lock(4242, state="asking")
    rows = [_session(1, "asking"), _session(2, "waiting")]
    assert len(escort.filter(rows)) == 2, "went silent over a session that is gone"
    assert escort.locked_on is None
    assert len(escort.filter(rows)) == 2


def test_the_escort_matches_a_pid_that_came_back_as_a_string():
    """Pids arrive as ints from sessions.json and as strings from anything that
    has been through a command line. Compared raw they never match, which looks
    exactly like a session that is not there."""
    escort = focus.Escort()
    escort.lock("2")
    assert [s["name"] for s in escort.filter([_session(1), _session(2, name="api")])] == ["api"]


def test_with_no_lock_the_escort_hands_back_everything():
    escort = focus.Escort()
    rows = [_session(1), _session(2)]
    assert escort.filter(rows) == rows
    assert escort.filter([]) == []


# ── the ladder ──

def test_the_rung_climbs_with_the_wait():
    ladder = focus.Insistence()
    rows = [_session(1, "asking")]
    assert ladder.update(rows, 0.0)[1] == 1
    assert ladder.update(rows, 119.0)[1] == 1
    assert ladder.update(rows, 120.0)[1] == 2
    assert ladder.update(rows, 300.0)[1] == 3


def test_the_rung_never_drops_while_the_session_still_wants_a_human():
    """The elapsed time cannot come from the session's own idleSeconds — the
    probe recomputes it every cycle and it falls whenever the session emits
    anything. A rung that falls back produces a character having a seizure."""
    ladder = focus.Insistence()
    rows = [_session(1, "asking")]
    ladder.update(rows, 0.0)
    assert ladder.update(rows, 400.0)[1] == 3
    assert ladder.update(rows, 100.0)[1] == 3, "the clock stepped back and it forgot"
    assert ladder.update(rows, 401.0)[1] == 3


def test_the_rung_resets_when_the_session_stops_wanting_a_human():
    """Answered and back to work, then asking again an hour later: the second
    summons starts by talking, not by waving."""
    ladder = focus.Insistence()
    ladder.update([_session(1, "asking")], 0.0)
    assert ladder.update([_session(1, "asking")], 600.0)[1] == 3
    assert ladder.update([_session(1, "working")], 610.0)[1] == 0
    assert ladder.update([_session(1, "asking")], 4000.0)[1] == 1


def test_asking_becoming_waiting_starts_the_ladder_over():
    """A question answered and a session finished are two summonses, not one
    long one."""
    ladder = focus.Insistence()
    ladder.update([_session(1, "asking")], 0.0)
    assert ladder.update([_session(1, "asking")], 400.0)[1] == 3
    assert ladder.update([_session(1, "waiting")], 401.0)[1] == 1


def test_without_the_opt_in_the_pointer_rung_never_appears():
    """Rung 4 takes the mouse out of the user's hand and cannot be undone by
    ignoring it. No amount of waiting buys it."""
    assert focus.insistence_level(60 * 60 * 24) == 3
    ladder = focus.Insistence()
    rows = [_session(1, "asking")]
    ladder.update(rows, 0.0)
    for hour in range(1, 25):
        assert ladder.update(rows, hour * 3600.0)[1] == 3, f"reached 4 after {hour}h"


def test_the_pointer_rung_needs_both_the_opt_in_and_the_wait():
    ladder = focus.Insistence(allow_pointer=True)
    rows = [_session(1, "asking")]
    ladder.update(rows, 0.0)
    assert ladder.update(rows, 599.0)[1] == 3
    assert ladder.update(rows, 600.0)[1] == 4


def test_withdrawing_the_opt_in_takes_effect_at_once():
    """The remembered rung must not outlive the permission that earned it, or
    turning the setting off leaves one last grab at the mouse."""
    ladder = focus.Insistence(allow_pointer=True)
    rows = [_session(1, "asking")]
    ladder.update(rows, 0.0)
    assert ladder.update(rows, 900.0)[1] == 4
    ladder.allow_pointer = False
    assert ladder.update(rows, 901.0)[1] == 3


def test_a_session_already_stuck_when_the_companion_starts_is_not_started_over():
    """Launch the companion at four and it finds a session that has been on a
    question since lunch. Beginning that one at rung 1 spends ten minutes
    talking politely about the most stuck thing on the desktop."""
    ladder = focus.Insistence(allow_pointer=True)
    stuck = dict(_session(1, "asking"), idleSeconds=3600)
    assert ladder.update([stuck], 5000.0)[1] == 3
    assert ladder.update([stuck], 5001.0)[1] == 3, "an hour on file bought the pointer"
    assert ladder.update([stuck], 5000.0 + focus.SEED_CAP)[1] == 4


def test_an_unknown_wait_does_not_silence_a_session_that_is_asking():
    """sessions-probe writes idleSeconds -1 when it cannot tell. Subtracted
    raw it puts the start of the wait in the future, and the ladder answers 0
    for the one state that must never be silent."""
    ladder = focus.Insistence()
    unknown = dict(_session(1, "asking"), idleSeconds=-1)
    assert ladder.update([unknown], 0.0)[1] == 1
    assert ladder.update([dict(_session(2, "asking"), idleSeconds=None)], 0.0)[2] == 1


def test_sessions_that_are_gone_are_forgotten():
    """A companion left running for days otherwise keeps one entry per pid
    that has ever existed."""
    ladder = focus.Insistence()
    ladder.update([_session(1, "asking"), _session(2, "waiting")], 0.0)
    ladder.update([_session(2, "waiting")], 10.0)
    assert list(ladder._seen) == [2]


# ── quiet hours ──

def test_no_history_does_not_silence_the_companion():
    """Day one has no peakHours at all. A companion that goes mute on its first
    day is broken, and nobody will work out why."""
    assert not focus.quiet_now({}, 3)
    assert focus.working_hours({}) is None
    assert focus.peak_hours({}) == {}
    assert focus.peak_hours({"lifetime": {"peakHours": None}}) == {}


def test_a_thin_history_does_not_silence_the_companion():
    """Two hours of use say nothing about the other twenty-two, and a rule
    applied to them anyway declares almost the whole day out of bounds."""
    thin = {14: 3, 15: 4}
    assert focus.working_hours(thin) is None
    for hour in range(24):
        assert not focus.quiet_now(thin, hour), f"silenced at {hour}:00 on two days of history"


def test_the_measured_history_marks_the_night_quiet_and_the_day_worked():
    """The real file: 538 observations over 18 hours, busiest 76 at 14:00."""
    worked = focus.working_hours(REAL_PEAK_HOURS)
    assert worked is not None
    for hour in (9, 11, 14, 17, 19):
        assert not focus.quiet_now(REAL_PEAK_HOURS, hour), f"{hour}:00 called quiet"
    for hour in (2, 4, 6, 23):
        assert focus.quiet_now(REAL_PEAK_HOURS, hour), f"{hour}:00 called a working hour"


def test_a_dip_in_the_middle_of_the_day_is_not_quiet_hours():
    """One hour below the bar between two worked ones is lunch. Left alone it
    produces a companion that shuts up for exactly one hour every afternoon,
    which reads as a bug rather than as tact."""
    lunch = {**REAL_PEAK_HOURS, 13: 1}
    assert not focus.quiet_now(lunch, 13)
    assert focus.quiet_now(lunch, 4), "filling holes swallowed the night"


def test_the_hour_wraps_instead_of_raising():
    """Callers hand in whatever localtime gave them; 24 must not be an
    IndexError in the middle of a poll."""
    assert focus.quiet_now(REAL_PEAK_HOURS, 24) == focus.quiet_now(REAL_PEAK_HOURS, 0)


def test_peak_hours_survives_junk_in_the_file():
    payload = {"lifetime": {"peakHours": {"9": 40, "bad": 5, "99": 5, "10": "x",
                                          "11": 0, "12": 12}}}
    assert focus.peak_hours(payload) == {9: 40, 12: 12}


# ── the idle probe ──

def test_the_idle_probe_answers_none_rather_than_zero_when_it_cannot_measure():
    """Zero means the person just typed and none means no idea. Handing back
    zero for a failed probe is how the companion goes permanently quiet on a
    desktop with no idle source — which is this desktop: XWayland here does not
    carry MIT-SCREEN-SAVER, measured, and KWin answers GetSessionIdleTime with
    NotSupported."""
    saved = focus._probe
    try:
        focus._probe = False
        assert focus.user_idle_seconds() is None
    finally:
        focus._probe = saved


def test_the_live_idle_probe_answers_a_number_or_nothing_at_all():
    """Whatever this machine has, the contract holds: never a negative, never
    a bare int standing in for a failure."""
    value = focus.user_idle_seconds()
    assert value is None or (isinstance(value, float) and value >= 0.0), value


# ── a payload that is wrong rather than absent ─────────────────────────────

def test_a_truthy_wrong_type_in_the_payload_does_not_raise():
    """`or {}` only catches the falsy, and that is the whole hole.

    A collector caught mid-write, or a payload hand-edited to `"lifetime": 1`,
    is valid JSON and truthy, so it walks straight past the guard and `.get`
    on an int raises. This is read from the companion's poll, and the failure
    is not one lost frame: the same file is still on disk twenty seconds
    later, so it raises again, and again, and the character never speaks for
    the rest of the session while walking around looking perfectly fine.
    """
    for payload in ({"lifetime": 1}, {"lifetime": "x"}, {"lifetime": []},
                    {"lifetime": {"peakHours": 7}}, {"lifetime": {"peakHours": "x"}},
                    1, "x", [], None, {}):
        assert focus.peak_hours(payload) == {}, payload


def test_a_real_payload_still_reads_after_the_type_checks():
    """The guard has to reject the junk without rejecting the data — a
    peak_hours that always answers {} passes the test above and silences
    quiet hours everywhere."""
    hours = focus.peak_hours({"lifetime": {"peakHours": {"9": 4, "14": 30, "3": 0}}})
    assert hours == {9: 4, 14: 30}, hours
