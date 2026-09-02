"""Three panels that state something instead of displaying something.

The widget was almost entirely "now": a bar for the weekly quota with no
projection, a list of sessions with no grouping, and a chart of eight days with
no verdict about the last one. The panels added for those three are cheap to
draw and easy to get subtly wrong, and every way of getting them wrong produces
a plausible-looking number rather than an error:

  - a rate of zero projected forward says "never", which is a claim about the
    future that no data here supports;
  - a projection past the reset, rendered as a date, turns good news into an
    alarm;
  - a UTC instant formatted with UTC getters names the wrong weekday for
    anybody west of Greenwich, and the percentage beside it is still right;
  - a partial day compared with whole days reads "below normal" at 11:00 every
    single day, which is a gauge that says the same thing whatever happens;
  - five days of history, two of them idle, will support a mean and a
    percentage that mean nothing.

pytest cannot load QML, and a regex over a binding expression cannot tell any
of that apart. So the arithmetic was written as free functions over plain
values inside main.qml — no `root.`, no Qt types, and the clock arrives as an
argument — and this file lifts those functions out of the real file (not a copy
of them) and runs them in node against numbers, the way tests/test_weekly_rows.py
already does for weeklyRows.

The checks that remain textual are the ones about the file rather than the
arithmetic: that both language tables carry every key, that the panels call the
functions tested here with the fields they were tested with, and that no label
in a fixed-width popup can push the layout wider than the declared minimum.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
QML = REPO / "plasmoid" / "contents" / "ui" / "main.qml"

# The pure functions. Everything the three panels compute lives in one of
# these; anything that has to reach for tr() or a theme colour stayed in the
# delegates and is checked textually further down.
PURE = (
    "weeklyForecast",
    "forecastZone",
    "calendarParts",
    "costsByProject",
    "dayFraction",
    "baselineComparison",
    "formatPctPerHour",
)

needs_node = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node not installed")


def _function_source(text, name):
    """The whole `function name(...) { ... }`, matched by counting braces.

    Anchoring on indentation would silently truncate at the first line that
    happens to be flush, and a truncated body still parses as JavaScript often
    enough to make the failure look like a logic bug.
    """
    at = text.find("function %s(" % name)
    assert at != -1, "function %s not found in main.qml" % name
    start = text.index("{", at)
    depth, i = 1, start + 1
    while i < len(text) and depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    assert depth == 0, "unterminated body for %s" % name
    return text[at:i]


@pytest.fixture(scope="session")
def module(tmp_path_factory):
    """The real function bodies, as a requireable CommonJS module."""
    src = QML.read_text()
    parts = [_function_source(src, name) for name in PURE]
    parts.append("module.exports = { %s };" % ", ".join(PURE))
    path = tmp_path_factory.mktemp("qmljs") / "sections.js"
    path.write_text("\n\n".join(parts))
    return path


@pytest.fixture(scope="session")
def call(module):
    """Evaluate one expression against those functions, under a chosen zone.

    TZ is a parameter because half of what is being checked here is that local
    time is used where the reader's calendar is meant, and a test that runs in
    whatever zone the machine happens to be in cannot see that at all.
    """
    node = shutil.which("node")

    def run(expr, tz="UTC"):
        prog = ("const F = require(%s); Object.assign(globalThis, F); "
                "process.stdout.write(JSON.stringify(%s));"
                % (json.dumps(str(module)), expr))
        # The environment is inherited and only TZ is overridden: node may be
        # under nvm, where a hand-built PATH cannot find its own libraries.
        r = subprocess.run([node, "-e", prog], capture_output=True, text=True,
                           env={**os.environ, "TZ": tz})
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)
    return run


# ── Payloads, as the collector actually emitted them ──────────────────
#
# Copied from ~/.claude/widget-data.json on 2026-09-02 rather than invented, so
# the shapes here are the shapes the widget reads: trend7d carries no cost,
# sessionCosts carries no timestamp, and the weekly bucket carries a percentage
# with no denominator.

LIVE_WEEKLY = {"percentUsed": 27.0, "resetsLabel": "Fri 05:00 AM",
               "resetsAt": "2026-09-04T05:00:00.108637+00:00"}
LIVE_BURN = 77499143

LIVE_TREND = [
    {"date": "2026-08-26", "label": "Wed", "tokens": 2437630634, "messages": 4408, "sessions": 18},
    {"date": "2026-08-27", "label": "Thu", "tokens": 805992616, "messages": 744, "sessions": 6},
    {"date": "2026-08-28", "label": "Fri", "tokens": 6256778401, "messages": 5302, "sessions": 5},
    {"date": "2026-08-29", "label": "Sat", "tokens": 0, "messages": 0, "sessions": 0},
    {"date": "2026-08-30", "label": "Sun", "tokens": 0, "messages": 0, "sessions": 0},
    {"date": "2026-08-31", "label": "Mon", "tokens": 3047861067, "messages": 5259, "sessions": 7},
    {"date": "2026-09-01", "label": "Tue", "tokens": 6683549347, "messages": 7487, "sessions": 129},
    {"date": "2026-09-02", "label": "Wed", "tokens": 1284709767, "messages": 1186, "sessions": 92},
]

LIVE_SESSION_COSTS = [
    {"id": "f02419e8", "project": "var/www/adb/tools", "messages": 469, "costUSD": 88.61, "tokens": 117708084},
    {"id": "b8e40305", "project": "var/www/DEBTHUB/2/1", "messages": 354, "costUSD": 80.79, "tokens": 118418116},
    {"id": "8e7adc74", "project": "home/ti/claude/usage/widget", "messages": 364, "costUSD": 78.01, "tokens": 119419079},
    {"id": "ab48b700", "project": "var/www/amaral/intern/hub", "messages": 240, "costUSD": 68.81, "tokens": 83068224},
    {"id": "68e9eb26", "project": "home/ti", "messages": 189, "costUSD": 41.51, "tokens": 55874682},
    {"id": "1d441931", "project": "tmp/tmp/8eqAowFnns/repo", "messages": 22, "costUSD": 0.59, "tokens": 330581},
]

HOUR = 3600000.0


def _ms(iso):
    """Epoch milliseconds for a UTC instant, derived rather than pasted.

    An earlier draft of this file carried hand-typed epoch constants and every
    one of them was a day out, which the arithmetic tests still passed around
    happily because a wrong-but-consistent clock is consistent.
    """
    from datetime import datetime
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


def _iso(ms):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


# A Wednesday afternoon, fixed: a test that reads the clock passes at one time
# of day and fails at another.
NOW = _ms("2026-09-02T18:20:00+00:00")
DAY0 = _ms("2026-09-02T00:00:00+00:00")
assert _iso(NOW).startswith("2026-09-02T18:20"), _iso(NOW)
assert _iso(DAY0).startswith("2026-09-02T00:00"), _iso(DAY0)


def _weekly(pct, elapsed_hours, now=NOW):
    """A weekly bucket whose reset places `now` that far into the window."""
    return {"percentUsed": pct, "resetsAt": _iso(now + (168 - elapsed_hours) * HOUR)}


# ── The instrument, before anything it reports is believed ────────────

@needs_node
def test_the_extractor_lifts_the_real_functions(call):
    """Every check below runs on text pulled out of main.qml by brace
    counting. If that pulled out the wrong span, or a stale copy, the numbers
    would still be internally consistent and every assertion would pass."""
    got = call("formatPctPerHour(0.2)")
    assert got == "0.20%/h", got
    shape = call("Object.keys(weeklyForecast(null, 0, 0)).sort()")
    assert "state" in shape and "hoursToLimit" in shape, shape

    # And it really is this file's code rather than a reimplementation that
    # drifted: the extracted text still carries main.qml's own comments.
    text = QML.read_text()
    body = _function_source(text, "weeklyForecast")
    assert "resetsAt is its far edge" in body, body[:300]
    for state in ("unknown", "atLimit", "noPace", "resetFirst", "limitFirst"):
        assert '"%s"' % state in body, state


def test_the_arithmetic_is_free_of_qml():
    """These functions are testable only for as long as they stay pure. A
    `root.` or a `Kirigami.` slipped into one of them does not break the
    widget, so nothing would report it — the function simply stops being
    liftable and every check above it goes dark."""
    text = QML.read_text()
    for name in PURE:
        body = _function_source(text, name)
        for forbidden in ("root.", "Kirigami.", "Qt.", "Plasmoid.", "Date.now()"):
            assert forbidden not in body, (
                "%s reaches for %s; it can no longer be evaluated outside a "
                "Plasma session, and the tests for it are now vacuous"
                % (name, forbidden))


# ── Delivery 1: the weekly projection ─────────────────────────────────

@needs_node
def test_live_payload_says_the_reset_arrives_first(call):
    """Today's real numbers: 27% spent with 34h40m of the window left. At the
    pace that produced that 27% the ceiling is a fortnight away, so the honest
    answer is that the week turns over long before it — not a date."""
    f = call("weeklyForecast(%s, %d, %d)" % (json.dumps(LIVE_WEEKLY), LIVE_BURN, NOW))
    assert f["state"] == "resetFirst", f
    assert f["elapsedHours"] == pytest.approx(133.3333, abs=1e-3), f
    assert f["pctPerHour"] == pytest.approx(27 / 133.3333, rel=1e-4), f
    assert f["hoursToLimit"] == pytest.approx(73 * 133.3333 / 27, rel=1e-4), f
    assert f["atMs"] > f["resetMs"]


@needs_node
def test_a_rate_of_zero_is_not_a_forecast_of_never(call):
    """The failure this guards: (100 - pct) / 0 is Infinity, and Infinity
    rendered through any date formatter becomes either a wrong date or the
    word "never". Neither is a statement this data can make."""
    idle = call("weeklyForecast(%s, 0, %d)" % (json.dumps(_weekly(27, 133.0)), NOW))
    assert idle["state"] == "noPace", idle
    assert idle["atMs"] == -1 and idle["hoursToLimit"] == -1, idle

    missing = call("weeklyForecast(%s, null, %d)" % (json.dumps(_weekly(27, 133.0)), NOW))
    assert missing["state"] == "noPace", missing

    untouched = call("weeklyForecast(%s, %d, %d)" % (json.dumps(_weekly(0, 133.0)), LIVE_BURN, NOW))
    assert untouched["state"] == "noPace", untouched
    assert untouched["pctPerHour"] == 0, untouched


@needs_node
def test_a_projection_past_the_reset_is_reported_as_the_reset(call):
    """Two scenarios either side of the exact crossing. They differ by twelve
    minutes of elapsed window and must produce two different sentences."""
    # e = 1.68 * pct puts the projected instant exactly on the reset.
    on = call("weeklyForecast(%s, 1, %d)" % (json.dumps(_weekly(50, 84.0)), NOW))
    assert on["state"] == "resetFirst", on
    assert on["atMs"] == pytest.approx(on["resetMs"], abs=1000), on

    later = call("weeklyForecast(%s, 1, %d)" % (json.dumps(_weekly(50, 84.2)), NOW))
    assert later["state"] == "resetFirst", later

    earlier = call("weeklyForecast(%s, 1, %d)" % (json.dumps(_weekly(50, 83.8)), NOW))
    assert earlier["state"] == "limitFirst", earlier
    assert earlier["atMs"] < earlier["resetMs"]


@needs_node
def test_the_ceiling_case_carries_the_hours_it_claims(call):
    """90% with 20h of window left: the arithmetic is 10 points at 90/148
    points an hour, and the panel colours itself on that number."""
    f = call("weeklyForecast(%s, 1, %d)" % (json.dumps(_weekly(90, 148.0)), NOW))
    assert f["state"] == "limitFirst", f
    assert f["hoursToLimit"] == pytest.approx(1480 / 90, rel=1e-6), f
    assert f["atMs"] == pytest.approx(NOW + (1480 / 90) * HOUR, abs=1000)


@needs_node
@pytest.mark.parametrize("weekly", [
    None,
    {"percentUsed": 27.0},                                    # no reset at all
    {"percentUsed": 27.0, "resetsAt": ""},                    # the empty scope
    {"percentUsed": 27.0, "resetsAt": "not a timestamp"},
    {"percentUsed": None, "resetsAt": "2026-09-04T05:00:00+00:00"},
])
def test_an_unusable_window_projects_nothing(call, weekly):
    """weeklyFable and weeklyScoped ship with resetsAt: "" when the API has
    nothing to report. Parsing that yields NaN, and NaN arithmetic propagates
    into a bar position and a date without ever raising."""
    f = call("weeklyForecast(%s, %d, %d)" % (json.dumps(weekly), LIVE_BURN, NOW))
    assert f["state"] == "unknown", f
    assert f["pctPerHour"] == 0, f


@needs_node
def test_a_reset_outside_the_window_is_refused_rather_than_scaled(call):
    """A reset already behind the clock, or further ahead than the window is
    long, means the timestamp and the machine disagree. Dividing by the
    implied elapsed time would silently rescale every number in the panel."""
    stale = call("weeklyForecast(%s, %d, %d)"
                 % (json.dumps(_weekly(27, 175.0)), LIVE_BURN, NOW))  # reset 7h ago
    assert stale["state"] == "unknown", stale

    ahead = call("weeklyForecast(%s, %d, %d)"
                 % (json.dumps(_weekly(27, -5.0)), LIVE_BURN, NOW))   # reset 173h out
    assert ahead["state"] == "unknown", ahead


@needs_node
def test_a_spent_week_says_so_instead_of_projecting(call):
    f = call("weeklyForecast(%s, %d, %d)" % (json.dumps(_weekly(100, 100.0)), LIVE_BURN, NOW))
    assert f["state"] == "atLimit", f
    assert call("forecastZone(%s)" % json.dumps(f)) == "alert"


@needs_node
def test_the_forecast_does_not_move_when_the_burn_rate_swings(call):
    """The damping, stated as a property rather than as a comment.

    burnRate.total_per_hour is instantaneous: a half-hour break halves it. If
    the projection were driven by it, the label would walk between weekdays
    between two refreshes. It is driven by the pace the week has actually kept,
    so an eightfold swing in the instantaneous rate moves nothing."""
    week = json.dumps(_weekly(70, 100.0))
    slow = call("weeklyForecast(%s, 5000000, %d)" % (week, NOW))
    fast = call("weeklyForecast(%s, 400000000, %d)" % (week, NOW))
    assert slow["state"] == fast["state"] == "limitFirst", (slow, fast)
    assert slow["atMs"] == fast["atMs"], (slow, fast)
    assert slow["pctPerHour"] == pytest.approx(0.7), slow


@needs_node
def test_the_label_bucket_survives_a_refresh(call):
    """The other half of the damping: the answer is rendered as a quarter of a
    day, so a projection that lands anywhere inside one produces the same
    words.

    The percentage the API reports is an integer, and one point of it moves the
    projected instant by roughly two hours. Here 70, 71 and 72 percent at the
    same point in the window land almost four hours apart and still read as the
    same Friday morning.

    What this does NOT claim: that the label never moves. Quantising trades a
    label that drifts continuously for one that steps at a boundary, and a
    projection sitting on 11:55 will step once to "afternoon". That is a step
    per boundary crossed instead of a step per refresh."""
    seen, instants = set(), []
    for pct in (70, 71, 72):
        f = call("weeklyForecast(%s, 1, %d)" % (json.dumps(_weekly(pct, 100.0)), NOW))
        assert f["state"] == "limitFirst", f
        instants.append(f["atMs"])
        q = call("calendarParts(%d, %d)" % (f["atMs"], NOW), tz="America/Sao_Paulo")
        seen.add((q["weekday"], q["part"]))
    spread = (max(instants) - min(instants)) / HOUR
    assert spread > 2, "the fixture no longer spreads the instants: %.2fh" % spread
    assert len(seen) == 1, "the label moved with the rounding: %s" % sorted(seen)


@needs_node
@pytest.mark.parametrize("hours,zone", [
    (12, "alert"), (23.9, "alert"), (24, "warn"), (71.9, "warn"),
    (72, "calm"), (400, "calm"),
])
def test_the_forecast_is_loud_in_hours_not_in_percent(call, hours, zone):
    f = {"state": "limitFirst", "hoursToLimit": hours}
    assert call("forecastZone(%s)" % json.dumps(f)) == zone


@needs_node
def test_a_calm_state_is_never_painted_as_an_alarm(call):
    for state in ("resetFirst", "noPace", "unknown"):
        f = {"state": state, "hoursToLimit": 2}
        assert call("forecastZone(%s)" % json.dumps(f)) == "calm", state


# ── The timezone, which is invisible when it is wrong ─────────────────

@needs_node
def test_the_calendar_is_the_readers_not_the_apis(call):
    """resetsAt is UTC. 2026-09-04T02:00Z is Friday in Greenwich and Thursday
    evening in Sao Paulo; naming it Friday there is wrong by a whole day, and
    the percentage printed beside it is still correct."""
    ms = _ms("2026-09-04T02:00:00+00:00")
    assert _iso(ms).startswith("2026-09-04T02:00"), _iso(ms)

    utc = call("calendarParts(%d, %d)" % (ms, NOW), tz="UTC")
    assert (utc["weekday"], utc["part"], utc["hour"]) == (5, "night", 2), utc

    sp = call("calendarParts(%d, %d)" % (ms, NOW), tz="America/Sao_Paulo")
    assert (sp["weekday"], sp["part"], sp["hour"]) == (4, "evening", 23), sp

    tokyo = call("calendarParts(%d, %d)" % (ms, NOW), tz="Asia/Tokyo")
    assert (tokyo["weekday"], tokyo["part"], tokyo["hour"]) == (5, "morning", 11), tokyo


@needs_node
@pytest.mark.parametrize("hour,part", [
    (0, "night"), (5, "night"), (6, "morning"), (11, "morning"),
    (12, "afternoon"), (17, "afternoon"), (18, "evening"), (23, "evening"),
])
def test_the_quarter_day_buckets_meet_without_a_gap(call, hour, part):
    """Every hour of the day belongs to exactly one bucket. An off-by-one at a
    boundary produces a label that is wrong for one hour in every four, which
    is not a frequency anybody notices."""
    got = call("calendarParts(%d, %d)" % (DAY0 + hour * HOUR, DAY0), tz="UTC")
    assert got["hour"] == hour, got
    assert got["part"] == part, got


# ── Delivery 2: where the money went ──────────────────────────────────

@needs_node
def test_todays_six_sessions_group_into_six_projects(call):
    """The calibrated case: one session per checkout, so grouping is very
    nearly the identity. It still has to be right — shares must total the day,
    and the order must be the cost order."""
    g = call("costsByProject(%s)" % json.dumps(LIVE_SESSION_COSTS))
    assert len(g) == 6, g
    assert [r["sessions"] for r in g] == [1] * 6
    assert [r["project"] for r in g][:2] == ["var/www/adb/tools", "var/www/DEBTHUB/2/1"]
    assert sum(r["share"] for r in g) == pytest.approx(1.0)
    total = sum(r["costUSD"] for r in LIVE_SESSION_COSTS)
    assert g[0]["share"] == pytest.approx(88.61 / total)
    assert [r["costUSD"] for r in g] == sorted((r["costUSD"] for r in g), reverse=True)


@needs_node
def test_repeated_sessions_in_one_checkout_become_one_row(call):
    """The case the panel exists for, which today's data does not contain."""
    rows = [
        {"id": "a", "project": "home/ti/widget", "costUSD": 10.0, "tokens": 100, "messages": 5},
        {"id": "b", "project": "home/ti/widget", "costUSD": 5.5, "tokens": 50, "messages": 3},
        {"id": "c", "project": "var/www/api", "costUSD": 12.0, "tokens": 20, "messages": 1},
        {"id": "d", "project": "home/ti/widget", "costUSD": 0.5, "tokens": 7, "messages": 2},
    ]
    g = call("costsByProject(%s)" % json.dumps(rows))
    assert [r["project"] for r in g] == ["home/ti/widget", "var/www/api"], g
    assert g[0]["sessions"] == 3
    assert g[0]["costUSD"] == pytest.approx(16.0)
    assert g[0]["tokens"] == 157 and g[0]["messages"] == 10
    assert g[0]["share"] == pytest.approx(16.0 / 28.0)


@needs_node
def test_the_project_string_is_not_split_into_a_hierarchy(call):
    """Claude's project directories collapse the path separator and a literal
    dash into the same "/": "home/ti/claude/usage/widget" is the repository
    claude-usage-widget, not a widget nested under a usage. Rolling up by the
    first two segments would merge it into "home/ti", inventing a parent that
    does not exist and hiding the checkout that spent the money."""
    g = call("costsByProject(%s)" % json.dumps(LIVE_SESSION_COSTS))
    names = [r["project"] for r in g]
    assert "home/ti" in names and "home/ti/claude/usage/widget" in names, names
    assert "var/www/adb/tools" in names and "var/www/amaral/intern/hub" in names, names
    assert len({n.split("/")[0] for n in names}) < len(names), (
        "the fixture no longer exercises the shared-prefix case")


@needs_node
def test_equal_costs_keep_a_fixed_order(call):
    """Sorting only on cost leaves ties to the engine, and the rows reshuffle
    under the reader's cursor on every refresh."""
    rows = [{"id": "1", "project": "zeta", "costUSD": 4.0},
            {"id": "2", "project": "alpha", "costUSD": 4.0},
            {"id": "3", "project": "mid", "costUSD": 4.0}]
    first = call("costsByProject(%s).map(r => r.project)" % json.dumps(rows))
    again = call("costsByProject(%s).map(r => r.project)" % json.dumps(list(reversed(rows))))
    assert first == ["alpha", "mid", "zeta"], first
    assert first == again, (first, again)


@needs_node
def test_a_session_with_no_project_still_has_a_row(call):
    rows = [{"id": "abcd1234", "costUSD": 3.0}, {"id": "e", "project": "", "costUSD": 1.0}]
    g = call("costsByProject(%s)" % json.dumps(rows))
    assert [r["project"] for r in g] == ["abcd1234", "e"], g


@needs_node
def test_a_costless_day_does_not_divide_by_zero(call):
    """A fresh account, or a day of cached reads only: every costUSD is 0 and
    the share is 0/0. NaN reaches a bar width and the row vanishes without an
    error anywhere."""
    rows = [{"id": "a", "project": "p", "costUSD": 0}, {"id": "b", "project": "q", "costUSD": 0}]
    g = call("costsByProject(%s)" % json.dumps(rows))
    assert [r["share"] for r in g] == [0, 0], g
    assert call("costsByProject([])") == []
    assert call("costsByProject(null)") == []


# ── Delivery 3: today against this account's own days ─────────────────

@needs_node
def test_the_partial_day_is_scaled_before_it_is_compared(call):
    """The defect this exists to prevent: comparing what today has spent by
    noon with what whole days spent means the panel reads "below normal" every
    morning of every day, which is not a measurement of anything.

    Constructed so the answer is exactly 1.0 when the scaling is right: today
    holds a quarter of the median and a quarter of the day has passed."""
    prior = [{"tokens": 100}, {"tokens": 200}, {"tokens": 300}]
    trend = prior + [{"tokens": 50}]          # median 200, quarter of it
    now = DAY0 + 6 * HOUR            # 06:00 UTC, a quarter of the day
    c = call("baselineComparison(%s, 'tokens', %d)" % (json.dumps(trend), now))
    assert c["state"] == "ok", c
    assert c["fraction"] == pytest.approx(0.25), c
    assert c["expected"] == pytest.approx(50.0), c
    assert c["ratio"] == pytest.approx(1.0), c
    assert c["verdict"] == "typical", c
    # Unscaled, the same day would have read 0.25x — a quarter of normal — and
    # would have done so every morning regardless of the work done.
    assert c["ratio"] != pytest.approx(50 / 200)


@needs_node
def test_a_day_three_hours_old_is_not_compared_at_all(call):
    """Below a couple of hours the scaled baseline approaches zero and the
    ratio against it explodes: one request at 00:10 reads as ten normal days.
    The threshold is two hours, so 01:00 refuses and 03:00 answers."""
    trend = [{"tokens": 100}, {"tokens": 200}, {"tokens": 300}, {"tokens": 5}]
    day = DAY0  # 2026-09-02T00:00:00Z

    early = call("baselineComparison(%s, 'tokens', %d)" % (json.dumps(trend), day + 1 * HOUR))
    assert early["state"] == "tooEarly", early
    assert early["ratio"] == 0, early

    midnight = call("baselineComparison(%s, 'tokens', %d)" % (json.dumps(trend), day))
    assert midnight["state"] == "tooEarly", midnight

    later = call("baselineComparison(%s, 'tokens', %d)" % (json.dumps(trend), day + 3 * HOUR))
    assert later["state"] == "ok", later


@needs_node
def test_under_three_active_days_there_is_no_verdict(call):
    """Two days is not a range, and a ratio against it is a number with the
    authority of a coin toss."""
    now = DAY0 + 12 * HOUR
    two = [{"tokens": 100}, {"tokens": 200}, {"tokens": 50}]
    c = call("baselineComparison(%s, 'tokens', %d)" % (json.dumps(two), now))
    assert c["state"] == "insufficient" and c["days"] == 2, c

    three = [{"tokens": 100}, {"tokens": 200}, {"tokens": 300}, {"tokens": 50}]
    ok = call("baselineComparison(%s, 'tokens', %d)" % (json.dumps(three), now))
    assert ok["state"] == "ok" and ok["days"] == 3, ok

    for short in ([], [{"tokens": 5}]):
        c = call("baselineComparison(%s, 'tokens', %d)" % (json.dumps(short), now))
        assert c["state"] == "insufficient", (short, c)


@needs_node
def test_idle_days_are_not_evidence_about_a_working_day(call):
    """Two of the eight real days are zeros — a weekend. Averaged in, they
    halve the baseline and every working day afterwards reads as a spike."""
    now = DAY0 + 12 * HOUR
    active = [{"tokens": 100}, {"tokens": 200}, {"tokens": 300}, {"tokens": 150}]
    with_idle = ([{"tokens": 100}, {"tokens": 0}, {"tokens": 200}, {"tokens": 0},
                  {"tokens": 300}, {"tokens": 150}])
    a = call("baselineComparison(%s, 'tokens', %d)" % (json.dumps(active), now))
    b = call("baselineComparison(%s, 'tokens', %d)" % (json.dumps(with_idle), now))
    assert a["days"] == b["days"] == 3, (a, b)
    assert a["median"] == b["median"] == 200, (a, b)
    assert a["lo"] == b["lo"] and a["hi"] == b["hi"], (a, b)


@needs_node
def test_the_centre_is_a_median_because_one_day_can_be_eight_times_another(call):
    """The real series runs 0.8B to 6.7B. A mean over five such days sits
    somewhere no day has ever been, and every comparison against it is wrong
    in the same direction."""
    now = DAY0 + 12 * HOUR
    trend = [{"tokens": 1}, {"tokens": 1}, {"tokens": 1}, {"tokens": 1},
             {"tokens": 100}, {"tokens": 1}]
    c = call("baselineComparison(%s, 'tokens', %d)" % (json.dumps(trend), now))
    assert c["median"] == 1, c            # the mean of those five is 20.8
    assert c["lo"] == pytest.approx(0.5) and c["hi"] == pytest.approx(50.0), c
    assert c["verdict"] == "typical", c   # 1 at half a day is 0.5, inside [0.5, 50]


@needs_node
@pytest.mark.parametrize("today,verdict", [
    (10, "below"),     # under the quietest prior day
    (49, "below"),
    (50, "typical"),   # exactly the quietest: inside the range, not below it
    (100, "typical"),
    (150, "typical"),  # exactly the busiest
    (151, "above"),
])
def test_the_verdict_is_a_rank_against_the_days_that_happened(call, today, verdict):
    """A percentage band would need a spread this sample cannot support. The
    claim made instead is one the data does support: inside or outside the
    range the prior active days actually spanned, scaled to the hour."""
    now = DAY0 + 12 * HOUR  # half the day
    trend = [{"tokens": 100}, {"tokens": 200}, {"tokens": 300}, {"tokens": today}]
    c = call("baselineComparison(%s, 'tokens', %d)" % (json.dumps(trend), now))
    assert (c["lo"], c["hi"]) == (50.0, 150.0), c
    assert c["verdict"] == verdict, c


@needs_node
def test_the_live_series_reads_as_a_normal_wednesday(call):
    """The real eight days, at local noon: five active prior days, a median of
    3.05B, and today's 1.28B sitting inside the band."""
    now = DAY0 + 12 * HOUR
    c = call("baselineComparison(%s, 'tokens', %d)" % (json.dumps(LIVE_TREND), now))
    assert c["state"] == "ok" and c["days"] == 5, c
    assert c["median"] == 3047861067, c
    assert c["value"] == 1284709767, c
    assert c["expected"] == pytest.approx(3047861067 / 2), c
    assert c["ratio"] == pytest.approx(1284709767 / (3047861067 / 2), rel=1e-9), c
    assert c["verdict"] == "typical", c


@needs_node
def test_messages_are_a_usable_axis_too(call):
    """trend7d carries no cost, so the only two series it can be compared on
    are tokens and messages. The panel picks tokens; the function must not
    have hard-coded it."""
    now = DAY0 + 12 * HOUR
    c = call("baselineComparison(%s, 'messages', %d)" % (json.dumps(LIVE_TREND), now))
    assert c["state"] == "ok" and c["value"] == 1186, c
    assert c["median"] == 5259, c


@needs_node
def test_the_day_fraction_is_local(call):
    """Local midnight, not UTC midnight. Read in UTC the same instant is a
    third of the way through the day and the baseline is a third of a day's
    work; read in Tokyo it is late evening and the baseline is nearly whole."""
    ms = DAY0 + 8 * HOUR  # 2026-09-02T08:00:00Z
    assert call("dayFraction(%d)" % ms, tz="UTC") == pytest.approx(8 / 24)
    assert call("dayFraction(%d)" % ms, tz="Asia/Tokyo") == pytest.approx(17 / 24)
    assert call("dayFraction(%d)" % ms, tz="America/Sao_Paulo") == pytest.approx(5 / 24)


# ── The file: what the panels do with all of that ─────────────────────

def _section(text, marker):
    """The block of main.qml that draws one panel, from its banner comment to
    the closing brace of the Rectangle it introduces."""
    at = text.index(marker)
    start = text.index("Rectangle {", at)
    depth, i = 1, text.index("{", start) + 1
    while i < len(text) and depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[at:i]


SECTIONS = ("── Weekly forecast ──", "── Cost by project ──",
            "── Today against your own days ──")


@pytest.mark.parametrize("marker", SECTIONS)
def test_each_panel_is_on_the_usage_page(marker):
    """Everything on this page lives inside providerPage, which is hidden when
    the harness page is showing. A panel outside it is drawn on top of the
    other page."""
    text = QML.read_text()
    page = text.index("id: providerPage")
    footer = text.index("── Footer ──")
    at = text.index(marker)
    assert page < at < footer, marker


@pytest.mark.parametrize("marker,call_expr", [
    ("── Weekly forecast ──", "root.weeklyForecast("),
    ("── Cost by project ──", "root.costsByProject("),
    ("── Today against your own days ──", "root.baselineComparison("),
])
def test_each_panel_calls_the_function_that_was_tested(marker, call_expr):
    """Otherwise the arithmetic above is verified and the panel is drawing
    something else."""
    block = _section(QML.read_text(), marker)
    assert call_expr in block, "%s does not call %s" % (marker, call_expr)


def _braced(text, at):
    """The block opened by the first brace at or after `at`."""
    start = text.index("{", at)
    depth, i = 1, start + 1
    while i < len(text) and depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[start:i]


def test_the_forecast_reads_the_fields_it_was_tested_with():
    block = _section(QML.read_text(), "── Weekly forecast ──")
    for field in ("rateLimits?.weeklyAll", "burnRate?.total_per_hour", "root.nowMs"):
        assert field in block, field


def test_every_forecast_state_has_its_own_sentence():
    """Scoped to the verdict expression, not to the panel.

    The looser version of this check — the state name appearing anywhere in
    the block — passed with the resetFirst branch deleted, because the name
    also occurs in the qualifier line below it. A branch that falls through
    shows the reader the sentence written for a different state, which is the
    one failure mode that must not be quiet: "the reset comes first" and
    "ceiling around Thursday" are opposite pieces of news.
    """
    block = _section(QML.read_text(), "── Weekly forecast ──")
    verdict = _braced(block, block.index("var f = fcCol.fc;") - 40)
    for state, key in (("atLimit", "ceilingReached"),
                       ("noPace", "noPaceToProject"),
                       ("resetFirst", "resetComesFirst"),
                       ("limitFirst", "ceilingAround")):
        assert '"%s"' % state in verdict, (
            "the verdict does not branch on %s" % state)
        assert 'tr("%s")' % key in verdict, (
            "state %s has no sentence of its own" % state)
    # And a fall-through for anything the function may return later.
    assert 'tr("noWindow")' in verdict, verdict


def test_the_comparison_reads_the_series_and_the_clock():
    block = _section(QML.read_text(), "── Today against your own days ──")
    assert "trend7d" in block and '"tokens"' in block and "root.nowMs" in block, block[:400]
    for state in ("tooEarly", "ok"):
        assert '"%s"' % state in block, state


def test_the_clock_that_feeds_the_projections_is_refreshed():
    """nowMs is the only dependency in those bindings that changes. Without a
    timer moving it, the forecast is computed once when the popup is built and
    then stands still while looking exactly as correct as a live one."""
    text = QML.read_text()
    assert re.search(r"property real nowMs: Date\.now\(\)", text), (
        "no nowMs property to drive the projections")
    at = text.index("property real nowMs")
    window = text[at:at + 500]
    assert "Timer {" in window, "nowMs is never refreshed"
    assert "root.nowMs = Date.now()" in window, window
    assert re.search(r"interval: 60000", window), window


# ── Width, which the popup cannot recover from ────────────────────────

def test_the_new_panels_carry_no_fixed_width_that_cannot_shrink():
    """The popup declares Layout.minimumWidth 20 grid units and its Flickable
    clips horizontally instead of scrolling, so a row that cannot compress
    below the preferred width does not overflow — it takes the popup with it,
    which is how a single extra header button clipped the whole thing once
    already.

    The rule checked: every label in these panels either has a small fixed
    width, or grows and elides. A growing label with no elide is the shape
    that breaks."""
    text = QML.read_text()
    for marker in SECTIONS:
        block = _section(text, marker)
        for m in re.finditer(r"Layout\.fillWidth: true", block):
            # The enclosing declaration: back to the previous line that opens
            # a QML item, forward to the end of its property list.
            tail = block[m.end():m.end() + 700]
            head = block[max(0, m.start() - 700):m.start()]
            opener = re.findall(r"(\w+)\s*\{", head)
            if not opener or opener[-1] != "Label" and "Label" not in opener[-1]:
                continue
            assert "Layout.minimumWidth: 0" in tail or "Layout.minimumWidth: 0" in head, (
                "%s: a growing label with no minimumWidth 0" % marker)
            assert "elide:" in tail or "elide:" in head, (
                "%s: a growing label with no elide" % marker)


@pytest.mark.parametrize("marker", SECTIONS)
def test_no_panel_pins_a_width_wider_than_the_popups_minimum(marker):
    """20 grid units, less two large spacings of page margin and two medium
    ones of card margin, leaves about 17 for a row. Anything approaching that
    in a single column has no room for the rest of the row."""
    block = _section(QML.read_text(), marker)
    for m in re.finditer(r"Layout\.(?:preferredWidth|minimumWidth):\s*"
                         r"Kirigami\.Units\.gridUnit\s*\*\s*([\d.]+)", block):
        assert float(m.group(1)) <= 8, (
            "%s pins %s grid units in one column" % (marker, m.group(1)))


# ── Both languages, and no emoji ──────────────────────────────────────

NEW_KEYS = (
    "weeklyForecast", "noPaceToProject", "resetComesFirst", "ceilingAround",
    "ceilingReached", "atWeekPace", "noWindow",
    "part_night", "part_morning", "part_afternoon", "part_evening",
    "wd0", "wd1", "wd2", "wd3", "wd4", "wd5", "wd6",
    "costByProject", "projects", "oneSessionEach", "todayVsUsual",
    "aboveYourRange", "withinYourRange", "belowYourRange",
    "medianOf", "activeDays", "adjustedForHour",
    "tooEarlyToCompare", "needMoreDays",
)


def _table(lang):
    """One language's string table, as key to value."""
    text = QML.read_text()
    at = text.index('"%s": {' % lang)
    start = text.index("{", at)
    depth, i = 1, start + 1
    while i < len(text) and depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    body = text[start:i]
    return dict(re.findall(r'"([A-Za-z0-9_]+)":\s*"((?:[^"\\]|\\.)*)"', body))


def test_the_table_parser_sees_the_real_tables():
    """A check over an empty dict passes."""
    en, pt = _table("en"), _table("pt")
    assert en.get("weeklyLimits") == "Weekly limits", en.get("weeklyLimits")
    assert pt.get("weeklyLimits") == "Limites semanais", pt.get("weeklyLimits")
    assert len(en) > 100 and len(pt) > 100, (len(en), len(pt))


@pytest.mark.parametrize("key", NEW_KEYS)
def test_every_new_string_exists_in_both_languages(key):
    """tr() falls back to English and then to the key itself, so a missing
    Portuguese entry shows an English word or a bare identifier on the page
    and raises nothing."""
    en, pt = _table("en"), _table("pt")
    assert key in en, "%s missing from the English table" % key
    assert key in pt, "%s missing from the Portuguese table" % key
    assert en[key].strip() and pt[key].strip(), key


def test_the_weekday_and_part_keys_match_what_the_label_builds():
    """whenLabel composes the key from a number and a bucket name. A weekday
    key that does not exist renders as the literal "wd3"."""
    body = _function_source(QML.read_text(), "whenLabel")
    assert 'tr("wd" + p.weekday)' in body, body
    assert 'tr("part_" + p.part)' in body, body
    en = _table("en")
    for i in range(7):
        assert "wd%d" % i in en
    for part in ("night", "morning", "afternoon", "evening"):
        assert "part_%s" % part in en


@pytest.mark.parametrize("marker", SECTIONS)
def test_no_emoji_reached_the_new_panels(marker):
    """Both spellings. A literal pictograph in the source is the obvious one;
    the one that slips through review is the escape, because "\\u{1F4B0}" is
    plain ASCII in the file and renders as a coin on the page."""
    block = _section(QML.read_text(), marker)
    literal = [c for c in block if ord(c) > 0x2100 and c not in "─══·×"]
    assert not literal, "%s carries %r" % (marker, literal)
    escaped = re.findall(r"\\u\{?0*([0-9A-Fa-f]{4,6})\}?", block)
    astral = [e for e in escaped if int(e, 16) > 0x2100]
    assert not astral, "%s escapes %r" % (marker, astral)
