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


# A busy history, the shape the machine this was written on actually has:
# eighteen hours touched, peak in the afternoon, almost nothing before 09:00.
PEAK_HOURS = {"9": 19, "10": 43, "11": 63, "12": 41, "13": 28, "14": 76,
              "15": 50, "16": 60, "17": 45, "18": 47, "19": 33, "20": 8}


# ── one scenario per key, positive and near-miss ───────────────────────────
#
# The near-miss is the same payload with the justifying number moved to the
# other side of its threshold. A negative built by emptying the payload would
# pass for a detector that fires on anything at all.

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
    correct answer; a signal here would be invented from no data."""
    assert signals.detect({}, {}) == []
    assert signals.detect({}, {}, NOON) == []


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
    assert signals.detect(None, None) == []
    assert signals.detect({"sessions": ["a string", 3, None]}, {}, NOON) == []


def test_one_broken_detector_does_not_take_the_others_with_it():
    """The guarantee that makes this safe to call from a timer. A detector
    that raises loses its own signal; it does not mute the companion."""
    def _boom(ctx):
        raise ValueError("field renamed upstream")

    original = signals._DETECTORS
    try:
        signals._DETECTORS = (_boom, signals._quota, _boom)
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
