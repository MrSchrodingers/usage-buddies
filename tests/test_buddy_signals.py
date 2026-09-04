"""What the two payloads justify saying, and the ways that goes wrong.

Three failure modes are worth a suite of their own.

A category nothing can reach. "twoRed" shipped with four English lines and four
Portuguese ones and no code path that could select it, because the method that
chose what to say read efficiency, compaction, tool use and the clock and never
read rateLimits. Eight written sentences that could not appear, and nothing
failed. The coverage tests here hold both directions: every key the detector
can emit has lines in both languages, and every category in the table except
the two deliberate fallbacks is named by a key.

An exception on a timer. This runs from a QTimer inside the companion, on files
a collector may be mid-write in, half-configured, or reporting null for a
number it could not compute. A KeyError there does not drop a frame; it stops
the companion ever speaking again.

A threshold that fires on nothing. Signals that are true all day are read as
decoration within an afternoon, so each one is tested against the number just
below its bar as well as the number above it.
"""
import datetime
import os
import re
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import buddy_signals as signals
from buddy_lines import LINES

# Categories that exist for a quiet desktop rather than for a trigger. They are
# what the companion falls back to when nothing fired, so they are the only two
# allowed to have no signal naming them.
FALLBACK_CATEGORIES = {"ambient", "philosophy"}

# Every key the detector can emit, derived from the priority table rather than
# read from a public alias in the module. buddy_signals used to export
# `KEYS = frozenset(PRIORITY)` for this suite alone: a documented public symbol
# no running program reached, which is the defect the AST scan in
# tests/test_companion_modes.py exists to catch.
KEYS = frozenset(signals.PRIORITY)

# A fixed point in time, so a suite run at 03:00 does not see different signals
# from one run at noon. The hour is resolved through localtime rather than
# hardcoded as an offset, because the peak-hours history is a local-time count
# and the machine running this is not necessarily on the same clock as the one
# it was written on.
_DAY = 1_700_000_000


def at_hour(hour):
    """A timestamp whose local hour is `hour`, in whatever zone this runs in."""
    for step in range(24 * 4):
        when = _DAY + step * 900
        if time.localtime(when).tm_hour == hour:
            return when
    raise AssertionError(f"no timestamp with local hour {hour}")


NOON, NIGHT, DEAD_HOUR = at_hour(13), at_hour(2), at_hour(5)


def _session(**over):
    """One row shaped like sessions-probe.py writes it."""
    row = {"pid": 1, "cwd": "/tmp/x", "name": "repo", "branch": "feature/x",
           "state": "working", "detail": "", "idleSeconds": 0, "background": 0,
           "ageSeconds": 600, "hasTranscript": True}
    row.update(over)
    return row


def _sessions(*rows, **over):
    payload = {"sessions": list(rows), "counts": {}, "total": len(rows),
               "attention": None, "generatedAt": ""}
    payload.update(over)
    return payload


def _stamp(when):
    """`when` as the ISO text a collector writes into generatedAt.

    Zone-aware, like both real writers, and built from the timestamp rather
    than typed, so a suite run in any zone produces a stamp that means the
    moment it was asked for.
    """
    return datetime.datetime.fromtimestamp(when).astimezone().isoformat()


# One hour before the reading. The collector that prompted all of this was
# dead for more than that, and it is past both payloads' thresholds with room
# to spare, so a scenario built on it does not become a threshold test by
# accident.
DEAD_FOR_AN_HOUR = 3600


# A busy history, the shape the machine this was written on actually has:
# eighteen hours touched, peak in the afternoon, almost nothing before 09:00.
PEAK_HOURS = {"9": 19, "10": 43, "11": 63, "12": 41, "13": 28, "14": 76,
              "15": 50, "16": 60, "17": 45, "18": 47, "19": 33, "20": 8}


# ── one scenario per key, positive and near-miss ───────────────────────────
#
# The near-miss is the same payload with the justifying number moved to the
# other side of its threshold. A negative built by emptying the payload would
# pass for a detector that fires on anything at all.
#
# A scenario is the argument list for detect() and is splatted into it: most
# are (sessions, usage, now), and the greeting carries the fourth argument that
# arms it. Anything reading SCENARIOS has to splat rather than unpack.

def _scenarios():
    quiet = _sessions(_session())
    return {
        "asking": (
            (_sessions(_session(state="asking", name="adb")), {}, NOON),
            (_sessions(_session(state="working", name="adb")), {}, NOON)),
        "waiting": (
            (_sessions(_session(state="waiting", idleSeconds=600)), {}, NOON),
            (_sessions(_session(state="working", idleSeconds=600)), {}, NOON)),
        "allQuiet": (
            (_sessions(_session(state="idle", background=0)), {}, NOON),
            (_sessions(_session(state="idle", background=2)), {}, NOON)),
        "idle": (
            (_sessions(_session(state="idle", background=2)), {}, NOON),
            (_sessions(_session(state="idle", background=0)), {}, NOON)),
        "background": (
            (_sessions(_session(state="background", background=2)), {}, NOON),
            (_sessions(_session(state="working", background=0)), {}, NOON)),
        "quotaHigh": (
            (quiet, {"rateLimits": {"session": {"percentUsed": 82}}}, NOON),
            (quiet, {"rateLimits": {"session": {"percentUsed": 79}}}, NOON)),
        "quotaCritical": (
            (quiet, {"rateLimits": {"session": {"percentUsed": 96}}}, NOON),
            (quiet, {"rateLimits": {"session": {"percentUsed": 94}}}, NOON)),
        "weeklyHigh": (
            (quiet, {"rateLimits": {"weeklyAll": {"percentUsed": 85}}}, NOON),
            (quiet, {"rateLimits": {"weeklyAll": {"percentUsed": 79}}}, NOON)),
        "twoRed": (
            (quiet, {"rateLimits": {"session": {"percentUsed": 97},
                                    "weeklyAll": {"percentUsed": 91}}}, NOON),
            (quiet, {"rateLimits": {"session": {"percentUsed": 97},
                                    "weeklyAll": {"percentUsed": 84}}}, NOON)),
        "limitSoon": (
            (quiet, {"limitEta": {"minutesToLimit": 20, "label": "~20m"}}, NOON),
            (quiet, {"limitEta": {"minutesToLimit": 90, "label": "~1h 30m"}}, NOON)),
        "creditsLow": (
            (quiet, {"rateLimits": {"extraUsage": {
                "enabled": True, "usedCredits": 465.0, "monthlyLimit": 500.0,
                "currency": "BRL", "outOfCredits": False}}}, NOON),
            (quiet, {"rateLimits": {"extraUsage": {
                "enabled": True, "usedCredits": 120.0, "monthlyLimit": 500.0,
                "currency": "BRL", "outOfCredits": False}}}, NOON)),
        "incident": (
            (quiet, {"serviceStatus": {"indicator": "major", "description": "x",
                                       "active_incidents": [
                                           {"name": "Elevated errors on the API",
                                            "status": "investigating"}]}}, NOON),
            (quiet, {"serviceStatus": {"indicator": "none",
                                       "description": "All Systems Operational",
                                       "active_incidents": []}}, NOON)),
        "mcpAuth": (
            (quiet, {"mcpAuthPending": ["github"]}, NOON),
            (quiet, {"mcpAuthPending": []}, NOON)),
        "errorsClimbing": (
            (quiet, {"errorRate": {"rate_limit": 5, "overloaded": 2, "total": 7}}, NOON),
            (quiet, {"errorRate": {"rate_limit": 2, "overloaded": 0, "total": 2}}, NOON)),
        "opusFallback": (
            (quiet, {"opusFallbacks": {"suspicious": True, "todayOpusRatio": 0.12,
                                       "weekOpusRatio": 0.61, "gap": 0.49}}, NOON),
            (quiet, {"opusFallbacks": {"suspicious": False, "todayOpusRatio": 0.61,
                                       "weekOpusRatio": 0.62, "gap": 0.0}}, NOON)),
        "slowResponses": (
            (quiet, {"latency": {"avgSeconds": 41.0, "sampleSize": 30}}, NOON),
            (quiet, {"latency": {"avgSeconds": 12.3, "sampleSize": 50}}, NOON)),
        "expensiveSession": (
            (quiet, {"sessionCosts": [
                {"id": "a", "project": "var/www/adb/tools", "costUSD": 300.0},
                {"id": "b", "project": "home/ti", "costUSD": 40.0},
                {"id": "c", "project": "srv/api", "costUSD": 20.0}]}, NOON),
            (quiet, {"sessionCosts": [
                {"id": "a", "project": "var/www/adb/tools", "costUSD": 120.0},
                {"id": "b", "project": "home/ti", "costUSD": 120.0},
                {"id": "c", "project": "srv/api", "costUSD": 120.0}]}, NOON)),
        "runwayShort": (
            (quiet, {"costProjection": {"runwayHours": 1.5, "usdPerHour": 12.0}}, NOON),
            (quiet, {"costProjection": {"runwayHours": 9.0, "usdPerHour": 12.0}}, NOON)),
        "recordSession": (
            (_sessions(_session(ageSeconds=36_000)),
             {"lifetime": {"longestSession": {"duration": 36_000_000}}}, NOON),
            (_sessions(_session(ageSeconds=3_600)),
             {"lifetime": {"longestSession": {"duration": 36_000_000}}}, NOON)),
        "cacheDrop": (
            (quiet, {"efficiency": {"cacheHitRate": 0.21}}, NOON),
            (quiet, {"efficiency": {"cacheHitRate": 0.98}}, NOON)),
        "compaction": (
            (quiet, {"compaction": {"count": 9}}, NOON),
            (quiet, {"compaction": {"count": 1}}, NOON)),
        "readRatio": (
            (quiet, {"efficiency": {"readPerOutput": 648.7}}, NOON),
            (quiet, {"efficiency": {"readPerOutput": 12.0}}, NOON)),
        "bashHeavy": (
            (quiet, {"toolUse": {"byTool": {"Bash": 900, "Read": 100}}}, NOON),
            (quiet, {"toolUse": {"byTool": {"Bash": 90, "Read": 10}}}, NOON)),
        "sessionSpread": (
            (_sessions(*[_session(pid=n) for n in range(5)]), {}, NOON),
            (_sessions(*[_session(pid=n) for n in range(2)]), {}, NOON)),
        "branchOpinion": (
            (_sessions(_session(branch="production")), {}, NOON),
            (_sessions(_session(branch="feature/x")), {}, NOON)),
        "streakDay": (
            (quiet, {"streak": {"days": 9, "includesToday": True}}, NOON),
            (quiet, {"streak": {"days": 3, "includesToday": True}}, NOON)),
        "offPeak": (
            (quiet, {"lifetime": {"peakHours": PEAK_HOURS}}, DEAD_HOUR),
            (quiet, {"lifetime": {"peakHours": PEAK_HOURS}}, NOON)),
        "nightOwl": (
            (quiet, {}, NIGHT),
            (quiet, {}, NOON)),
        # Both payloads an hour past being written, against both of them
        # written a minute ago. The near-miss is a minute rather than a
        # second because a minute is inside both thresholds and outside the
        # measured cadence of either file: a healthy desktop really does hand
        # a reader a payload that old.
        "staleData": (
            (_sessions(_session(), generatedAt=_stamp(NOON - DEAD_FOR_AN_HOUR)),
             {"generatedAt": _stamp(NOON - DEAD_FOR_AN_HOUR)}, NOON),
            (_sessions(_session(), generatedAt=_stamp(NOON - 60)),
             {"generatedAt": _stamp(NOON - 60)}, NOON)),
        # The only scenario with a fourth element, and the only signal whose
        # justification is not in either payload: no file records that the
        # process has just started, so the caller says so. The near-miss is the
        # same desktop with the flag down, which is every poll after the first.
        "greeting": (
            (quiet, {}, NOON, True),
            (quiet, {}, NOON, False)),
    }


SCENARIOS = _scenarios()


def fired(scenario):
    return {signal.key: signal for signal in signals.detect(*scenario)}


# ── the dead-category traps ────────────────────────────────────────────────

@pytest.mark.parametrize("lang", ["en", "pt"])
def test_a_signal_without_lines_would_print_nothing(lang):
    """Every key the detector can emit has to exist in the table, or the
    companion picks a category, finds no sentences and stays silent while
    something was worth saying."""
    missing = sorted(KEYS - set(LINES[lang]))
    assert not missing, f"{lang} has no lines for: {missing}"


@pytest.mark.parametrize("lang", ["en", "pt"])
def test_a_category_nothing_can_trigger_is_dead_text(lang):
    """The twoRed defect, in the direction that produced it: four lines per
    language sitting in the table with no code path able to select them."""
    orphans = sorted(set(LINES[lang]) - KEYS - FALLBACK_CATEGORIES)
    assert not orphans, f"{lang} categories no signal can reach: {orphans}"


def test_every_key_is_reachable_from_real_data():
    """A key in the priority table that no payload can produce is the same
    dead text one level down: the category has lines, and nothing fires it."""
    reachable = set()
    for positive, _ in SCENARIOS.values():
        reachable |= set(fired(positive))
    unreachable = sorted(KEYS - reachable)
    assert not unreachable, f"no scenario produces: {unreachable}"


@pytest.mark.parametrize("key", sorted(KEYS))
def test_every_placeholder_is_filled_by_the_signal(key):
    """A line with a placeholder the signal does not supply prints the braces.

    Checked against the vars the detector actually emitted rather than against
    a declared list, so a detector that stops passing a variable fails here
    instead of on the desktop.
    """
    signal = fired(SCENARIOS[key][0])[key]
    for lang in ("en", "pt"):
        for line in LINES[lang][key]:
            for placeholder in re.findall(r"{(\w+)}", line):
                assert placeholder in signal.vars, \
                    f"{lang}/{key}: nothing fills {{{placeholder}}}"


# ── each signal against its own threshold ──────────────────────────────────

@pytest.mark.parametrize("key", sorted(SCENARIOS))
def test_the_signal_fires_on_the_data_that_justifies_it(key):
    assert key in fired(SCENARIOS[key][0]), f"{key} did not fire on its own data"


@pytest.mark.parametrize("key", sorted(SCENARIOS))
def test_the_signal_stays_quiet_just_below_its_threshold(key):
    """The near-miss payload is the same shape with the number on the other
    side of the bar. A signal that fires on both is decoration."""
    assert key not in fired(SCENARIOS[key][1]), f"{key} fired on the near-miss"


def test_a_critical_quota_does_not_also_report_itself_as_high():
    """quotaHigh and quotaCritical describe the same window. Firing both means
    the caller takes the louder one every time and the milder category is
    written, tested and never seen."""
    keys = fired((_sessions(), {"rateLimits": {"session": {"percentUsed": 99}}}, NOON))
    assert "quotaCritical" in keys
    assert "quotaHigh" not in keys


def test_an_empty_cache_hit_rate_is_missing_data_and_not_a_collapse():
    """The collector writes 0 when it has nothing to divide, and 0% cache
    would otherwise be the loudest possible reading of an empty day."""
    assert "cacheDrop" not in fired((_sessions(), {"efficiency": {"cacheHitRate": 0}}, NOON))


def test_credits_are_only_low_when_extra_usage_can_spend_them():
    """Measured on this machine: 0.01 left, extraUsage.enabled false. Those
    cents are not spendable, and reporting them is an alarm that can never be
    cleared."""
    off = {"rateLimits": {"extraUsage": {"enabled": False, "usedCredits": 499.0,
                                         "monthlyLimit": 500.0, "currency": "BRL",
                                         "outOfCredits": False}}}
    assert "creditsLow" not in fired((_sessions(), off, NOON))


def test_running_out_of_credits_is_reported_even_with_the_switch_off():
    """outOfCredits is the collector saying the ceiling was reached, which is
    the one case where the enabled flag says nothing useful."""
    out = {"rateLimits": {"extraUsage": {"enabled": False, "outOfCredits": True,
                                         "currency": "BRL"}}}
    assert "creditsLow" in fired((_sessions(), out, NOON))


def test_a_rounded_away_runway_is_not_an_emergency():
    """costProjection divides a credit balance by an estimated USD/hour and
    rounds to one decimal, so a residual balance in another currency lands on
    0.0 — measured here as 0.01 BRL against $17/h. Reading that as "no runway"
    pins a permanent warning to the screen."""
    zero = {"costProjection": {"runwayHours": 0.0, "usdPerHour": 17.089}}
    assert "runwayShort" not in fired((_sessions(), zero, NOON))


def test_a_slow_average_over_three_answers_is_not_a_trend():
    thin = {"latency": {"avgSeconds": 60.0, "sampleSize": 3}}
    assert "slowResponses" not in fired((_sessions(), thin, NOON))


def test_a_first_day_history_does_not_make_the_whole_clock_unusual():
    """peakHours on a fresh install is two hours and a handful of counts. Any
    rule applied to that declares twenty-two hours off-peak on no evidence."""
    fresh = {"lifetime": {"peakHours": {"14": 6, "15": 9}}}
    assert "offPeak" not in fired((_sessions(), fresh, DEAD_HOUR))


def test_the_hour_the_person_actually_works_beats_the_fixed_night_window():
    """offPeak is derived from this account's own history and nightOwl is a
    guess about everyone's, so when both fire the derived one is picked."""
    scenario = (_sessions(), {"lifetime": {"peakHours": PEAK_HOURS}}, NIGHT)
    keys = [signal.key for signal in signals.detect(*scenario)]
    assert "offPeak" in keys and "nightOwl" in keys
    assert keys.index("offPeak") < keys.index("nightOwl")


# ── the order, which is the whole product ──────────────────────────────────

def test_a_question_outranks_a_burning_quota_which_outranks_a_lecture():
    """The ladder in one assertion. A session that asked something waits
    forever and only a person unblocks it; a quota about to run out changes
    what you do next; how much of the day was Bash does not."""
    scenario = (
        _sessions(_session(state="asking", name="adb")),
        {"rateLimits": {"session": {"percentUsed": 98}},
         "toolUse": {"byTool": {"Bash": 900, "Read": 100}}},
        NOON)
    keys = [signal.key for signal in signals.detect(*scenario)]
    assert keys.index("asking") < keys.index("quotaCritical") < keys.index("bashHeavy")


def test_the_order_is_the_priority_and_not_the_order_detectors_run():
    scenario = (
        _sessions(_session(state="asking"), _session(state="waiting", pid=2),
                  _session(state="background", background=1, pid=3)),
        {"rateLimits": {"session": {"percentUsed": 99}},
         "serviceStatus": {"indicator": "major", "description": "Degraded",
                           "active_incidents": []},
         "compaction": {"count": 40}},
        NOON)
    found = signals.detect(*scenario)
    assert [signal.priority for signal in found] == sorted(s.priority for s in found)
    assert found[0].key == "asking"


# ── nothing raises, whatever is in the files ───────────────────────────────

def test_two_empty_payloads_say_nothing_rather_than_guessing():
    """First run, before either collector has written anything. Silence is the
    correct answer; a signal here would be invented from no data.

    Pinned to a fixed hour. The version of this that called detect() with no
    timestamp asserted an empty list against the wall clock, so it passed all
    day and failed between midnight and 05:00 on nightOwl — a test that
    reports the hour it was run at rather than the thing it was written to
    check. The no-argument call is still made, because the default clock is a
    code path, and what is asserted about it is what is actually true: it
    raises nothing and invents nothing beyond the hour it was run at.
    """
    assert signals.detect({}, {}, NOON) == []
    assert {signal.key for signal in signals.detect({}, {})} <= {"offPeak", "nightOwl"}


def test_nulls_where_numbers_belong_do_not_raise():
    """The collector writes null for anything it could not compute — a rate
    limit it has no source for, a ratio with nothing to divide. Arithmetic on
    those is a TypeError inside a QTimer, which is a companion that never
    speaks again."""
    usage = {
        "rateLimits": {"session": {"percentUsed": None, "resetsInMinutes": None},
                       "weeklyAll": {"percentUsed": None},
                       "extraUsage": {"enabled": True, "usedCredits": None,
                                      "monthlyLimit": None},
                       "credits": {"amount": None}},
        "limitEta": {"minutesToLimit": None, "label": None},
        "efficiency": {"cacheHitRate": None, "readPerOutput": None},
        "compaction": {"count": None},
        "toolUse": {"byTool": {"Bash": None, "Read": None}},
        "errorRate": {"total": None},
        "latency": {"avgSeconds": None, "sampleSize": None},
        "health": {"latencySeconds": None},
        "opusFallbacks": {"suspicious": None, "todayOpusRatio": None},
        "costProjection": {"runwayHours": None},
        "sessionCosts": [{"id": None, "project": None, "costUSD": None}],
        "lifetime": {"longestSession": {"duration": None}, "peakHours": {"9": None}},
        "streak": {"days": None, "includesToday": None},
        "serviceStatus": {"indicator": None, "active_incidents": [None]},
        "mcpAuthPending": [None],
    }
    sessions = _sessions(_session(name=None, branch=None, state=None,
                                  idleSeconds=None, background=None,
                                  ageSeconds=None), total=None)
    assert signals.detect(sessions, usage, NOON) == []


def test_wrong_types_where_blocks_belong_do_not_raise():
    """A truncated write, a hand-edited file, an older schema: the payload can
    be a list where a dict belongs, and reading it must degrade to silence."""
    usage = {"rateLimits": [], "limitEta": "soon", "efficiency": None,
             "toolUse": {"byTool": []}, "sessionCosts": {"a": 1},
             "lifetime": {"peakHours": ["9", "10"]}, "mcpAuthPending": "github",
             "serviceStatus": {"active_incidents": "none"}, "streak": 7}
    assert signals.detect("not a payload", usage, NOON) == []
    assert signals.detect(None, None, NOON) == []
    assert signals.detect({"sessions": ["a string", 3, None]}, {}, NOON) == []


def test_one_broken_detector_does_not_take_the_others_with_it():
    """The guarantee that makes this safe to call from a timer. A detector
    that raises loses its own signal; it does not mute the companion."""
    def _boom(ctx):
        raise ValueError("field renamed upstream")

    original = signals._DETECTORS
    try:
        signals._DETECTORS = ((_boom, signals.USAGE), (signals._quota, signals.USAGE),
                              (_boom, signals.CLOCK))
        found = signals.detect(_sessions(),
                               {"rateLimits": {"session": {"percentUsed": 97}}}, NOON)
    finally:
        signals._DETECTORS = original
    assert [signal.key for signal in found] == ["quotaCritical"]


# ── one histogram, one verdict ─────────────────────────────────────────────

def test_off_peak_and_the_focus_engine_never_disagree_about_an_hour():
    """Both modules read lifetime.peakHours, and for a while both decided for
    themselves what it meant. Measured against a real history the two rules
    disagreed at 20:00: buddy_focus counted the hour as worked while the
    off-peak signal called it unusual, so the companion would have remarked on
    the odd hour in the middle of what it treated as the working day.

    Nothing raises when two thresholds drift apart, and the only symptom is a
    mascot contradicting itself for one hour a day. This walks the whole clock
    so a future tuning of either rule cannot reopen the gap quietly.
    """
    import buddy_focus

    hours = {int(k): v for k, v in PEAK_HOURS.items()}
    disagreed = []
    for hour in range(24):
        when = at_hour(hour)
        off_peak = "offPeak" in fired(
            (_sessions(), {"lifetime": {"peakHours": PEAK_HOURS}}, when))
        if off_peak != buddy_focus.quiet_now(hours, hour):
            disagreed.append(hour)
    assert not disagreed, f"off-peak and quiet_now disagree at {disagreed}"


def test_a_thin_history_leaves_every_hour_alone_in_both_modules():
    """The shared reading returns None rather than an empty set when it cannot
    tell, and an empty set would put all twenty-four hours off-peak."""
    import buddy_focus

    fresh = {"14": 6, "15": 9}
    assert buddy_focus.working_hours({int(k): v for k, v in fresh.items()}) is None
    for hour in (2, 5, 13, 20):
        assert "offPeak" not in fired(
            (_sessions(), {"lifetime": {"peakHours": fresh}}, at_hour(hour)))


# ── a reading that stopped being a reading ─────────────────────────────────
#
# The defect these were written against was measured rather than imagined. On
# 2026-09-03 the Codex collector died with an AttributeError on every run and
# went more than an hour without writing widget-data.json, and for that whole
# hour the widget and the companion kept serving the last numbers as current.
# Nothing said anything; the person noticed by looking at the screen. Both
# payloads had carried `generatedAt` the entire time and no code read it.

def _aged(arguments, sessions_age, usage_age):
    """The same scenario with each payload stamped that many seconds old.

    Both ages are given explicitly and separately, because the two files are
    written by different processes on different cadences and the whole
    question below is what happens when one of them stops and the other does
    not.
    """
    when = arguments[2]
    sessions, usage = dict(arguments[0]), dict(arguments[1])
    sessions["generatedAt"] = _stamp(when - sessions_age)
    usage["generatedAt"] = _stamp(when - usage_age)
    return (sessions, usage) + tuple(arguments[2:])


def _clock_keys():
    """Every key a detector tagged CLOCK can emit, derived from the table.

    Listed here as a set literal it would be a second copy of the sources,
    and the copy is what drifts: a detector moved from CLOCK to USAGE would
    leave this suite asserting that a signal survives a dead collector after
    the module had stopped letting it.
    """
    original = signals._DETECTORS
    found = set()
    try:
        signals._DETECTORS = tuple(entry for entry in original
                                   if entry[1] is signals.CLOCK)
        for scenario in SCENARIOS.values():
            found |= set(fired(_aged(scenario[0], DEAD_FOR_AN_HOUR,
                                     DEAD_FOR_AN_HOUR)))
    finally:
        signals._DETECTORS = original
    return found


def test_a_minute_old_is_still_a_reading_and_an_hour_old_is_not():
    """The two ends of the verdict, against both thresholds.

    A minute is inside both limits and outside the measured write cadence of
    either file, so a healthy desktop really does hand a reader a payload that
    old; an hour is the outage that prompted this.
    """
    for limit in signals.STALE_AFTER.values():
        recent = signals.freshness({"generatedAt": _stamp(NOON - 60)}, NOON,
                                   stale_after=limit)
        assert recent.state == "fresh", limit
        assert recent.age == "1min"
        dead = signals.freshness({"generatedAt": _stamp(NOON - DEAD_FOR_AN_HOUR)},
                                 NOON, stale_after=limit)
        assert dead.state == "stale", limit
        assert dead.age == "1h"


def test_each_payload_is_judged_against_its_own_cadence():
    """One threshold for both files would be wrong for one of them.

    sessions.json is written every 19-20 s by the plasmoid's own timer;
    widget-data.json every 27-90 s by two systemd timers whose runs take up
    to forty seconds. Five minutes is a dead probe and an ordinary collector,
    and the two constants exist precisely so that reading says so.
    """
    five_minutes = {"generatedAt": _stamp(NOON - 300)}
    assert signals.freshness(five_minutes, NOON,
                             stale_after=signals.SESSIONS_STALE_SECONDS).state == "stale"
    assert signals.freshness(five_minutes, NOON,
                             stale_after=signals.USAGE_STALE_SECONDS).state == "fresh"
    assert set(signals.stale_payloads(five_minutes, five_minutes, NOON)) == {"sessions"}


@pytest.mark.parametrize("value", [
    None, "", "   ", "\t\n", 1_700_000_000, 1.5, True, [], {}, ["2026-09-04"],
    {"iso": "2026-09-04"}, "not a date", "yesterday", "2026-13-45T99:99:99",
    "2026-09-04T01:05:09+99:99", "2026-09-04T01:05:09-03:00 (BRT)",
])
def test_a_stamp_the_parser_cannot_read_is_unknown_and_never_raises(value):
    """`generatedAt` is text written by another process and read from a
    QTimer. Every way it can be wrong has to end in a verdict, because one
    raise there does not drop a frame — it costs every line the companion
    would ever have said.

    Unknown is deliberately not an accusation. A payload nobody has written
    yet is an empty dict with no numbers in it, so there is nothing to
    suppress, and a collector too old to stamp its output would otherwise be
    denounced forever — a permanent alarm is one nobody reads. The failure
    this exists for leaves a stamp behind and stops refreshing it.
    """
    for limit in signals.STALE_AFTER.values():
        assert signals.freshness({"generatedAt": value}, NOON,
                                 stale_after=limit) == signals.Freshness(
                                     "unknown", None, "")
    payload = {"generatedAt": value}
    assert signals.stale_payloads(payload, payload, NOON) == {}
    assert "staleData" not in fired((_sessions(_session(), generatedAt=value),
                                     payload, NOON))


def test_a_missing_stamp_is_unknown_rather_than_an_accusation():
    """The field absent altogether, which is every payload written before any
    of this existed."""
    for limit in signals.STALE_AFTER.values():
        assert signals.freshness({}, NOON, stale_after=limit).state == "unknown"
        assert signals.freshness({"sessions": []}, NOON,
                                 stale_after=limit).state == "unknown"


def test_a_stamp_without_a_zone_is_read_as_local_and_not_as_utc():
    """Reading a zoneless local stamp as UTC ages a payload written this
    second by the size of the offset — three hours on this machine — and
    calls it dead on every cycle, which is the alarm-that-cries-always the
    whole feature exists to avoid.

    The zone is forced rather than inherited: on a machine already running on
    UTC the two readings coincide and the assertion would pass without
    testing anything.
    """
    previous = os.environ.get("TZ")
    try:
        # A POSIX zone string rather than a name, so this does not depend on
        # a tzdata package being installed. "XXX3" is three hours behind UTC.
        os.environ["TZ"] = "XXX3"
        time.tzset()
        now = time.time()
        naive = datetime.datetime.fromtimestamp(now).isoformat()
        assert "+" not in naive and naive.count("-") == 2, naive
        verdict = signals.freshness({"generatedAt": naive}, now,
                                    stale_after=signals.SESSIONS_STALE_SECONDS)
        assert verdict.state == "fresh", verdict
        assert verdict.seconds < 1.0, verdict
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()


@pytest.mark.parametrize("ahead", [30, 3600, 86_400])
def test_a_stamp_in_the_future_is_a_disagreement_and_not_a_claim_of_freshness(ahead):
    """A clock that ran backwards is information, not an error: it says the
    two clocks disagree. Calling that fresh is the same lie inverted, and
    calling it stale is a sentence — "the data is -1h old" — that cannot be
    said. So it is neither, and it accuses nobody: a bad clock is not a dead
    collector, and there is no honest number to print.
    """
    stamp = {"generatedAt": _stamp(NOON + ahead)}
    for limit in signals.STALE_AFTER.values():
        verdict = signals.freshness(stamp, NOON, stale_after=limit)
        assert verdict.state == "ahead", verdict
        assert verdict.seconds < 0
        assert verdict.age == ""
    assert signals.stale_payloads(stamp, stamp, NOON) == {}
    assert "staleData" not in fired((_sessions(_session(), **stamp), stamp, NOON))


def test_a_stamp_a_moment_ahead_is_rounding_and_not_a_broken_clock():
    """Both writers share this machine's clock, so a sub-second future value
    is the write landing between the stamp and the read. Calling that a clock
    disagreement would put every payload into the one verdict that asserts
    nothing at all."""
    stamp = {"generatedAt": _stamp(NOON + 1)}
    assert signals.freshness(stamp, NOON,
                             stale_after=signals.USAGE_STALE_SECONDS).state == "fresh"


# ── the refusal, and its limits ────────────────────────────────────────────

@pytest.mark.parametrize("key", sorted(set(SCENARIOS) - {"staleData"}))
def test_no_number_survives_the_file_that_produced_it_going_quiet(key):
    """Every scenario in the suite, replayed with both payloads an hour old.

    What is left has to be the signals that assert no measurement — the hour,
    the greeting, and the verdict itself — because everything else is
    arithmetic on figures nobody can vouch for. The surviving set is derived
    from the detector table rather than listed here, so a detector that
    changes source changes this test with it.
    """
    dead = _aged(SCENARIOS[key][0], DEAD_FOR_AN_HOUR, DEAD_FOR_AN_HOUR)
    keys = set(fired(dead))
    assert "staleData" in keys, f"{key}: an hour-old payload was not called stale"
    assert keys <= _clock_keys(), f"{key}: still asserted {sorted(keys - _clock_keys())}"


def test_the_hour_and_the_greeting_are_not_punished_for_the_collector():
    """The three signals that never quoted a number. offPeak reads
    lifetime.peakHours, which is a count of every hour this account has ever
    worked — an hour without a rewrite cannot move it — and what it says is
    about the clock now. Silencing those alongside the numbers would be
    punishing the readings that did not go wrong.
    """
    dead = _aged((_sessions(), {"lifetime": {"peakHours": PEAK_HOURS}}, NIGHT, True),
                 DEAD_FOR_AN_HOUR, DEAD_FOR_AN_HOUR)
    keys = set(fired(dead))
    assert {"greeting", "offPeak", "nightOwl", "staleData"} <= keys, sorted(keys)


def test_the_two_payloads_go_stale_independently():
    """They are written by different processes on different cadences, so one
    dying says nothing about the other. A session that stopped to ask a
    question is still asking it while the usage collector is down, and a quota
    at 97% is still at 97% while the session probe is down; silencing either
    because the other went quiet would be its own invented conclusion.
    """
    both = (_sessions(_session(state="asking", name="adb")),
            {"rateLimits": {"session": {"percentUsed": 97}}}, NOON)

    alive = set(fired(_aged(both, 60, 60)))
    assert {"asking", "quotaCritical"} <= alive
    assert "staleData" not in alive

    probe_dead = set(fired(_aged(both, DEAD_FOR_AN_HOUR, 60)))
    assert "staleData" in probe_dead
    assert "asking" not in probe_dead, "a question was reported off a dead probe"
    assert "quotaCritical" in probe_dead, "a live quota was silenced by the probe"

    collector_dead = set(fired(_aged(both, 60, DEAD_FOR_AN_HOUR)))
    assert "staleData" in collector_dead
    assert "quotaCritical" not in collector_dead, "a quota was quoted off a dead file"
    assert "asking" in collector_dead, "a live question was silenced by the collector"


def test_a_question_off_a_live_probe_still_outranks_the_dead_collector():
    """Where staleData sits on the ladder, in the case that decides it. The
    argument for putting the verdict at the very top is that everything below
    it is made of numbers that no longer hold; the answer is that the two
    files age separately, so a question read out of a payload written twenty
    seconds ago is a live fact and the person it is waiting for outranks the
    news that a different file stopped."""
    both = (_sessions(_session(state="asking", name="adb")),
            {"rateLimits": {"session": {"percentUsed": 97}}}, NOON)
    keys = [signal.key for signal in signals.detect(*_aged(both, 60, DEAD_FOR_AN_HOUR))]
    assert keys.index("asking") < keys.index("staleData")


def test_a_burning_quota_off_a_live_collector_outranks_the_dead_probe():
    """The other half of the same decision. The band that means the ability to
    keep working is about to end only fires on a payload that is still being
    written, so it is a live reading and sits above the verdict; everything
    below the verdict is diagnosis and does not."""
    both = (_sessions(_session(state="idle", background=0)),
            {"rateLimits": {"session": {"percentUsed": 97}},
             "compaction": {"count": 40}}, NOON)
    keys = [signal.key for signal in signals.detect(*_aged(both, DEAD_FOR_AN_HOUR, 60))]
    assert keys.index("quotaCritical") < keys.index("staleData")
    assert keys.index("staleData") < keys.index("compaction")


def test_the_age_reported_is_the_older_of_the_two_files():
    """One category, two files. Saying twelve minutes while half the data is
    three hours old is the same understatement one level in."""
    quiet = (_sessions(_session()), {}, NOON)
    assert fired(_aged(quiet, 3 * 3600, 12 * 60))["staleData"].vars["age"] == "3h"
    assert fired(_aged(quiet, 12 * 60, 3 * 3600))["staleData"].vars["age"] == "3h"
    assert fired(_aged(quiet, 60, 2 * 3600))["staleData"].vars["age"] == "2h"


def test_every_detector_names_the_payload_its_claim_rests_on():
    """The suppression is by source. A detector added to the sweep without one
    would go on reporting numbers out of a file that stopped being written,
    which is the defect itself reintroduced by omission — and the tuple shape
    is what makes that impossible to do quietly."""
    allowed = {signals.SESSIONS, signals.USAGE, signals.CLOCK}
    for entry in signals._DETECTORS:
        assert isinstance(entry, tuple) and len(entry) == 2, entry
        detector, source = entry
        assert callable(detector), entry
        assert source in allowed, f"{detector.__name__} claims source {source!r}"
    listed = [detector for detector, _ in signals._DETECTORS]
    assert len(set(listed)) == len(listed), "a detector is in the sweep twice"


def test_the_verdict_has_a_key_the_ladder_knows_about():
    """STALE_KEY is spelled once and read by the companion. A drift between it
    and the priority table would raise inside _signal, be swallowed by the
    per-detector guard, and simply never say anything."""
    assert signals.STALE_KEY in signals.PRIORITY
    assert set(signals.STALE_AFTER) == {"sessions", "usage"}
