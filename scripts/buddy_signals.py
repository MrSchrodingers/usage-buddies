"""What the data says is worth mentioning, with no opinion about wording.

Pure by design: no Qt, no files, no clock of its own. `detect` is handed the
two payloads the companion already reads — ~/.cache/usage-buddies/sessions.json
and ~/.claude/widget-data.json — plus the current time, and returns every
signal that fires, most urgent first. It never picks a sentence and never sees
a language: the caller takes the first signal and looks the key up in
buddy_lines.LINES.

Why a separate module at all. The decision used to live inside a method that
also owned rotation, the no-repeat window and the Qt object it hung off, so the
only way to ask "would this desktop produce a quota warning" was to build a
Brain. The measurable consequence was a category — "twoRed", eight written
lines across two languages — that no code path could reach, because the same
method read efficiency, compaction, tool use and the hour, and never once read
rateLimits. A table of keys with a test that every key fires is what makes that
kind of dead text impossible to add quietly.

Two rules hold everywhere below.

Nothing raises. Both files are written by a collector that can be mid-write,
half-configured or reporting `null` for a number it could not compute, and this
runs on a QTimer: one KeyError there does not lose a frame, it loses every line
the companion would ever have said. Each detector is called inside its own
guard, so the worst case is one missing signal rather than a mute companion.

Every threshold is a named constant with the reason for the number next to it.
A bare `>= 0.7` in the middle of a condition is unarguable-with: the next
person cannot tell whether it was measured, inherited or typed.
"""
from __future__ import annotations

import time
from collections import namedtuple

# The one reading of lifetime.peakHours lives there; see the off-peak note
# below for why this module does not keep a second one.
import buddy_focus

# key: which category of buddy_lines.LINES says this.
# priority: lower is more urgent; the caller takes the first.
# vars: the placeholders that category's lines use, already formatted.
Signal = namedtuple("Signal", "key priority vars")


# ── the ladder ─────────────────────────────────────────────────────────────
#
# Ordering is the whole product here, so it lives in one table rather than in
# the order of a chain of ifs. Bands are ten apart with gaps inside them, so a
# new signal can be slotted between two existing ones without renumbering.
PRIORITY = {
    # 10 — a person is blocked right now. A session that stopped to ask
    # something waits forever and only a human unblocks it, so nothing
    # outranks it, including the account being about to run out of quota.
    "asking": 10,

    # 20 — the ability to keep working is about to end, and the window is
    # short enough that hearing it now changes what you do next. Below a
    # question, above every diagnosis: a quota that runs out in an hour is
    # worth interrupting a cache-hit lecture for, and is not worth
    # interrupting a person who is being waited on.
    "twoRed": 20,
    "quotaCritical": 22,
    "incident": 24,
    "limitSoon": 26,
    "creditsLow": 28,

    # 40 — a session wants a human, but nothing is on fire. Same order the
    # companion has always used: finished first, then stopped-with-nothing-
    # running, then idle, then background work, which is information rather
    # than a summons.
    "waiting": 40,
    "allQuiet": 44,
    "idle": 46,
    "background": 50,

    # 60 — diagnosis. True for hours, actionable at leisure, and repeated too
    # often it becomes wallpaper. Standing conditions live here even when they
    # need a human (mcpAuth): they will still be true in ten minutes, and
    # putting them above a finished session buries an event under a state.
    "quotaHigh": 60,
    "weeklyHigh": 62,
    "mcpAuth": 64,
    "errorsClimbing": 66,
    "opusFallback": 68,
    "slowResponses": 70,
    "cacheDrop": 72,
    "compaction": 74,
    "readRatio": 76,
    "bashHeavy": 78,
    "runwayShort": 80,
    "expensiveSession": 82,
    "recordSession": 84,
    "sessionSpread": 86,

    # 88 — remarks. Nothing is wrong; these exist so a quiet desktop is not
    # answered with the same three ambient lines forever.
    "branchOpinion": 88,
    "streakDay": 90,
    "offPeak": 92,
    "nightOwl": 94,
}

# The vocabulary. Anything outside this set is a typo, and a key in here that
# no scenario can produce is dead text of exactly the kind this module exists
# to prevent — tests/test_buddy_signals.py holds both ends of that.
KEYS = frozenset(PRIORITY)


# ── thresholds ─────────────────────────────────────────────────────────────

# Quota, as a percentage of the five-hour window. 80 is where the remaining
# fifth is about an hour of the same pace: long enough to change plans, short
# enough that saying so is not noise. 95 is where the next long turn is the one
# that gets cut off — at 90 there is still a working session's worth left, and
# a warning that leaves room to ignore it teaches people to ignore it.
QUOTA_HIGH_PCT = 80.0
QUOTA_CRITICAL_PCT = 95.0

# The weekly window gets the same bar and no critical twin: it resets days
# away, so there is no "act in the next few minutes" version of it.
WEEKLY_HIGH_PCT = 80.0

# Two windows both this deep is the twoRed case. Above the high bar and below
# critical, because the point is the coincidence rather than either number.
RED_PCT = 90.0

# limitEta is the collector's own projection of when the session window hits
# 100% at the current burn (predict_limit_eta, and it returns nothing at all
# beyond ten hours). 45 minutes is roughly a long turn plus reading the result:
# below it you cannot start something substantial and expect to finish it.
LIMIT_SOON_MINUTES = 45

# Extra usage, as a share of the monthly ceiling. 0.9 leaves a tenth, which is
# the last point where hearing about it is still a decision rather than news.
CREDITS_LOW_SHARE = 0.9

# errorRate counts API errors over a two-hour window (calculate_error_rate
# takes hours=2). One 429 or 529 is invisible retry noise; five in two hours is
# retries eating turns, which is felt as slowness with no explanation.
ERRORS_IN_WINDOW = 5

# Latency. There is no per-account latency baseline in the data to compare
# against — compute_health records the current average and flags errors and
# model mix, not slow answers — so this is an absolute number, chosen against a
# measured normal: on the machine this was written on, latency.avgSeconds was
# 12.3 over 50 samples. 30 is the round number a normal day here does not
# reach, and it is also about the point where a person stops waiting and
# switches windows. The sample floor stops a two-answer morning being called a
# trend.
SLOW_SECONDS = 30.0
SLOW_MIN_SAMPLES = 10

# One session dominating the day's cost. The absolute figures in sessionCosts
# are API-equivalent prices for a subscription user and run to hundreds on a
# busy day, so a flat "over $50" would fire every afternoon and mean nothing.
# The observation is disproportion: over half of today in one place, with a
# floor so it is not half of nothing, and a minimum count because one session
# is trivially 100% of one session.
EXPENSIVE_SHARE = 0.5
EXPENSIVE_MIN_USD = 25.0
EXPENSIVE_MIN_SESSIONS = 3

# Credit runway, in hours. Two is short enough to be about this afternoon.
RUNWAY_SHORT_HOURS = 2.0

# lifetime.longestSession.duration comes from Claude Code's own stats cache and
# is in milliseconds: the record on this machine reads 2,414,502,094 for a
# 1,247-message session, which is 28 days as milliseconds and 76 years as
# seconds. Firing at 80% of the record means the remark lands while the session
# is still running rather than after it is over. The floor rejects a record so
# small that everything beats it.
RECORD_MS_PER_HOUR = 3_600_000.0
RECORD_FRACTION = 0.8
RECORD_MIN_HOURS = 1.0

# Off-peak reads lifetime.peakHours (a count per hour of the day, hours with no
# activity absent rather than zero) through buddy_focus.working_hours, which is
# the one place that turns that histogram into a set of hours.
#
# It had its own rule here, and the two disagreed. Measured against this
# machine's real history the disagreement was one hour wide: at 20:00
# buddy_focus counted the hour as worked while this module called it unusual,
# so the companion would joke about the hour being odd during what it otherwise
# treated as the working day. Two thresholds over one histogram cannot be kept
# in step by intention; there is one definition now, and the disagreement is
# gone by construction rather than by both being tuned to the same numbers.

# Night, kept as the fixed window it has always been. offPeak is the better
# instrument — it is this person's hours rather than a guess about everyone's —
# so it sorts above this one and wins when both fire; this stays because it
# still says something true on an account with no history to derive from.
NIGHT_START, NIGHT_END = 0, 5

# A streak worth mentioning. Seven is the first length that is not "you also
# worked yesterday".
STREAK_NOTABLE_DAYS = 7

# Branches where a commit is not a private event. Opinion, not alarm: it sits
# at the bottom of the ladder and only speaks when nothing else does.
RISKY_BRANCHES = ("main", "master", "production", "prod", "trunk", "release")

# Carried over from the companion unchanged, so moving the decision out of
# Brain.line() cannot change what a given desktop says. Each was chosen when
# the line was written: a cache hit under 30% means something is invalidating
# the prefix, five compactions is context thrown away repeatedly, 300 read
# tokens per output token is reading a library to write a postcard, and 70% of
# calls being one tool only means anything once there are enough calls to have
# a shape.
CACHE_DROP_MAX = 0.3
COMPACTION_MIN = 5
READ_RATIO_MIN = 300
BASH_SHARE = 0.7
BASH_MIN_CALLS = 200
SESSION_SPREAD_MIN = 4


# ── reading whatever is actually in the file ───────────────────────────────

def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _num(value):
    """A float, or None when the field is missing, null or not a number.

    Booleans are rejected on purpose: `True` is an int in Python, and a flag
    that ended up where a percentage belongs would otherwise read as 1%.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _block(usage, *path):
    """A nested dict from the usage payload, or {} at the first thing missing."""
    node = _dict(usage)
    for key in path:
        node = _dict(node.get(key))
    return node


def format_idle(seconds):
    """Seconds as the companion has always shown them: 45s, 9min, 3h.

    Kept here rather than imported so this module stays free of Qt; it mirrors
    _fmt_idle in the companion, which can go once the companion reads its lines
    from signals.
    """
    value = _num(seconds) or 0.0
    value = int(max(value, 0))
    if value < 60:
        return f"{value}s"
    if value < 3600:
        return f"{value // 60}min"
    return f"{value // 3600}h"


def _signal(key, **vars_):
    return Signal(key, PRIORITY[key], vars_)


def _rows(sessions):
    return [row for row in _list(_dict(sessions).get("sessions"))
            if isinstance(row, dict)]


def _in_state(rows, *states):
    return [row for row in rows if _text(row.get("state")) in states]


def _name(row):
    return _text(row.get("name")) or "?"


_Context = namedtuple("_Context", "sessions usage rows now hour")


# ── the detectors ──────────────────────────────────────────────────────────
#
# One function per concern, each returning a list. They are independent: a
# detector that cannot answer returns [] and the rest still run.

def _sessions_wanting_a_human(ctx):
    found = []
    asking = _in_state(ctx.rows, "asking")
    if asking:
        found.append(_signal("asking", name=_name(asking[0])))

    waiting = _in_state(ctx.rows, "waiting")
    if waiting:
        found.append(_signal("waiting", name=_name(waiting[0]),
                             idle=format_idle(waiting[0].get("idleSeconds"))))

    # A session that stopped *and* has nothing left running is the one worth
    # calling finished. Quiet with an agent still going is not the same news.
    for row in _in_state(ctx.rows, "idle"):
        key = "idle" if (_num(row.get("background")) or 0) > 0 else "allQuiet"
        if key not in {sig.key for sig in found}:
            found.append(_signal(key, name=_name(row),
                                 idle=format_idle(row.get("idleSeconds"))))

    busy = _in_state(ctx.rows, "background")
    if busy:
        found.append(_signal("background", name=_name(busy[0]),
                             n=int(_num(busy[0].get("background")) or 1)))
    return found


def _quota(ctx):
    limits = _block(ctx.usage, "rateLimits")
    found = []

    session = _num(_dict(limits.get("session")).get("percentUsed"))
    if session is not None:
        if session >= QUOTA_CRITICAL_PCT:
            found.append(_signal("quotaCritical", n=round(session)))
        elif session >= QUOTA_HIGH_PCT:
            # Only below critical: both firing means the caller picks the
            # louder one and the milder line never appears, which is a
            # category that exists and cannot be reached.
            found.append(_signal("quotaHigh", n=round(session)))

    weekly = _num(_dict(limits.get("weeklyAll")).get("percentUsed"))
    if weekly is not None and weekly >= WEEKLY_HIGH_PCT:
        found.append(_signal("weeklyHigh", n=round(weekly)))

    # The windows that can be red at the same time. Labels are short and
    # numeric on purpose: they are printed into both languages.
    scoped = _dict(limits.get("weeklyScoped"))
    windows = [
        ("5h", _num(_dict(limits.get("session")).get("percentUsed"))),
        ("7d", weekly),
    ]
    # The model-scoped weekly window is only nameable when the payload says
    # which model it is for; without that it would print as a second "7d".
    if _text(scoped.get("modelName")):
        windows.append((_text(scoped.get("modelName")), _num(scoped.get("percentUsed"))))
    red = sorted(((label, pct) for label, pct in windows
                  if pct is not None and pct >= RED_PCT),
                 key=lambda pair: -pair[1])
    if len(red) >= 2:
        found.append(_signal("twoRed", a=red[0][0], b=red[1][0]))
    return found


def _limit_eta(ctx):
    eta = _block(ctx.usage, "limitEta")
    minutes = _num(eta.get("minutesToLimit"))
    if minutes is None or minutes < 0 or minutes > LIMIT_SOON_MINUTES:
        return []
    # The collector writes a label with the projection; falling back to the
    # raw number keeps the line readable if it ever writes one without.
    return [_signal("limitSoon", eta=_text(eta.get("label")) or f"{int(minutes)}min")]


def _credits(ctx):
    extra = _block(ctx.usage, "rateLimits", "extraUsage")
    currency = _text(extra.get("currency"))
    used = _num(extra.get("usedCredits"))
    limit = _num(extra.get("monthlyLimit"))

    if extra.get("outOfCredits") is True:
        return [_signal("creditsLow", v=f"0 {currency}".strip())]
    # A balance only matters when extra usage is switched on. With it off the
    # residual cents sitting in the account are not spendable, and reporting
    # them is a permanent false alarm — measured: this account reads 0.01 with
    # extraUsage.enabled false.
    if extra.get("enabled") is not True:
        return []
    if used is None or limit is None or limit <= 0:
        return []
    if used / limit < CREDITS_LOW_SHARE:
        return []
    left = max(limit - used, 0.0)
    return [_signal("creditsLow", v=f"{left:.0f} {currency}".strip())]


def _incident(ctx):
    status = _block(ctx.usage, "serviceStatus")
    for incident in _list(status.get("active_incidents")):
        what = _text(_dict(incident).get("name"))
        if what:
            # The bubble is one short sentence; a status page title can be a
            # paragraph, and an overlong line is cropped rather than wrapped.
            return [_signal("incident", what=what[:52].rstrip(" .,"))]
    # The overall indicator moves before an incident is filed, and after it is
    # resolved but not yet cleared. "none" is the healthy value.
    indicator = _text(status.get("indicator"))
    if indicator and indicator != "none":
        return [_signal("incident",
                        what=(_text(status.get("description")) or indicator)[:52])]
    return []


def _mcp_auth(ctx):
    pending = [_text(name) for name in _list(_dict(ctx.usage).get("mcpAuthPending"))]
    names = [name for name in pending if name]
    return [_signal("mcpAuth", name=names[0])] if names else []


def _errors(ctx):
    total = _num(_block(ctx.usage, "errorRate").get("total"))
    if total is None or total < ERRORS_IN_WINDOW:
        return []
    return [_signal("errorsClimbing", n=int(total))]


def _opus_fallback(ctx):
    fallbacks = _block(ctx.usage, "opusFallbacks")
    if fallbacks.get("suspicious") is not True:
        return []
    # The threshold behind the flag lives in the collector: today's Opus share
    # more than 25 points below the trailing week, with a week baseline of at
    # least 20%. It only sets the flag when both ratios exist, so a missing
    # number here means the payload is inconsistent and there is nothing to say.
    ratio = _num(fallbacks.get("todayOpusRatio"))
    if ratio is None:
        return []
    return [_signal("opusFallback", n=round(ratio * 100))]


def _slow(ctx):
    latency = _block(ctx.usage, "latency")
    average = _num(latency.get("avgSeconds"))
    samples = _num(latency.get("sampleSize"))
    if average is None:
        # health carries the same average by construction; it is the one that
        # survives when the latency block is absent.
        average = _num(_block(ctx.usage, "health").get("latencySeconds"))
    if average is None or average < SLOW_SECONDS:
        return []
    if samples is None or samples < SLOW_MIN_SAMPLES:
        return []
    return [_signal("slowResponses", n=round(average))]


def _expensive_session(ctx):
    costs = [row for row in _list(_dict(ctx.usage).get("sessionCosts"))
             if isinstance(row, dict)]
    priced = [(row, _num(row.get("costUSD")) or 0.0) for row in costs]
    if len(priced) < EXPENSIVE_MIN_SESSIONS:
        return []
    total = sum(cost for _, cost in priced)
    row, top = max(priced, key=lambda pair: pair[1])
    if total <= 0 or top < EXPENSIVE_MIN_USD or top / total < EXPENSIVE_SHARE:
        return []
    # sessionCosts names a path, not a repository: "var/www/adb/tools".
    project = _text(row.get("project")).strip("/")
    name = project.split("/")[-1] if project else (_text(row.get("id")) or "?")
    return [_signal("expensiveSession", name=name, usd=f"{top:.2f}")]


def _runway(ctx):
    hours = _num(_block(ctx.usage, "costProjection").get("runwayHours"))
    # Zero is excluded deliberately. The projection divides a credit balance by
    # an estimated USD/hour and rounds to one decimal, so a residual balance in
    # a currency that is not USD comes out as 0.0 — measured: 0.01 BRL against
    # $17/h on this machine. Reading that as "no runway left" puts a permanent
    # alarm on the screen for an account that is not spending credits at all.
    if hours is None or hours <= 0 or hours > RUNWAY_SHORT_HOURS:
        return []
    return [_signal("runwayShort", h=f"{hours:.1f}".rstrip("0").rstrip("."))]


def _record_session(ctx):
    record = _num(_block(ctx.usage, "lifetime", "longestSession").get("duration"))
    if record is None:
        return []
    record_hours = record / RECORD_MS_PER_HOUR
    if record_hours < RECORD_MIN_HOURS:
        return []
    ages = [_num(row.get("ageSeconds")) or 0.0 for row in ctx.rows]
    if not ages:
        return []
    hours = max(ages) / 3600.0
    if hours < record_hours * RECORD_FRACTION:
        return []
    return [_signal("recordSession", h=int(hours))]


def _diagnostics(ctx):
    """The four readings that were already in the companion, unchanged."""
    found = []
    efficiency = _block(ctx.usage, "efficiency")

    hit = _num(efficiency.get("cacheHitRate"))
    if hit is not None and 0 < hit < CACHE_DROP_MAX:
        found.append(_signal("cacheDrop", n=round(hit * 100)))

    compactions = _num(_block(ctx.usage, "compaction").get("count"))
    if compactions is not None and compactions >= COMPACTION_MIN:
        found.append(_signal("compaction", n=int(compactions)))

    ratio = _num(efficiency.get("readPerOutput"))
    if ratio is not None and ratio >= READ_RATIO_MIN:
        found.append(_signal("readRatio", n=round(ratio)))

    tools = _dict(_block(ctx.usage, "toolUse").get("byTool"))
    counts = {name: _num(count) or 0.0 for name, count in tools.items()}
    total = sum(counts.values())
    if total > BASH_MIN_CALLS:
        name, count = max(counts.items(), key=lambda pair: pair[1])
        if name == "Bash" and count / total > BASH_SHARE:
            found.append(_signal("bashHeavy", n=round(100 * count / total)))
    return found


def _session_spread(ctx):
    running = _num(_dict(ctx.sessions).get("total")) or 0
    if running < SESSION_SPREAD_MIN:
        return []
    name = _name(ctx.rows[0]) if ctx.rows else "?"
    return [_signal("sessionSpread", n=int(running), name=name)]


def _branch_opinion(ctx):
    for row in ctx.rows:
        branch = _text(row.get("branch"))
        if branch.lower() in RISKY_BRANCHES:
            return [_signal("branchOpinion", branch=branch, name=_name(row))]
    return []


def _streak(ctx):
    streak = _block(ctx.usage, "streak")
    days = _num(streak.get("days"))
    if days is None or days < STREAK_NOTABLE_DAYS:
        return []
    if streak.get("includesToday") is not True:
        return []
    return [_signal("streakDay", n=int(days))]


def _hour_of_day(ctx):
    found = []
    hours = {}
    for key, value in _block(ctx.usage, "lifetime", "peakHours").items():
        hour, count = _num(key), _num(value)
        if hour is None or count is None or not 0 <= hour <= 23:
            continue
        if count > 0:
            hours[int(hour)] = count
    # None, not an empty set, is what working_hours returns when the history is
    # too thin to say anything — and an empty set would put every hour of the
    # day off-peak, which is the failure this distinction exists to prevent.
    worked = buddy_focus.working_hours(hours)
    if worked is not None and ctx.hour not in worked:
        found.append(_signal("offPeak"))

    if NIGHT_START <= ctx.hour < NIGHT_END:
        found.append(_signal("nightOwl"))
    return found


_DETECTORS = (
    _sessions_wanting_a_human,
    _quota,
    _limit_eta,
    _credits,
    _incident,
    _mcp_auth,
    _errors,
    _opus_fallback,
    _slow,
    _expensive_session,
    _runway,
    _record_session,
    _diagnostics,
    _session_spread,
    _branch_opinion,
    _streak,
    _hour_of_day,
)


def detect(sessions, usage, now=None):
    """Every signal the two payloads justify, most urgent first.

    `sessions` is the sessions.json payload and `usage` the widget-data.json
    one; either may be empty, partial or wrong-typed. `now` is a Unix
    timestamp, defaulting to the wall clock — passed in so the hour-of-day
    signals can be tested without waiting for midnight.

    Returns a list, never None, and raises nothing. The caller takes the first
    entry; the rest are there so a caller that wants to skip a category it has
    said too recently has somewhere to go.
    """
    when = time.time() if now is None else (_num(now) or time.time())
    ctx = _Context(sessions=_dict(sessions), usage=_dict(usage),
                   rows=_rows(sessions), now=when,
                   hour=time.localtime(when).tm_hour)
    found = []
    for detector in _DETECTORS:
        try:
            found.extend(detector(ctx) or [])
        except Exception:
            # One detector failing costs its own signal and nothing else. This
            # runs on a timer: an exception escaping here is not a dropped
            # frame, it is a companion that never speaks again.
            continue
    return sorted(found, key=lambda signal: (signal.priority, signal.key))


def quota_fraction(usage):
    """The five-hour window as a fraction of itself, or None when unknown.

    None and 0.0 are different answers and the difference is visible: a caller
    drawing an hourglass from this renders "nothing used yet" as a full glass,
    which is exactly what an account with no rate-limit data would show if this
    returned zero for missing. A genuine 0.0 — a window that has just reset —
    does return 0.0.

    The five-hour window rather than the weekly one because it is the one that
    empties and refills within a sitting; the weekly figure is a different
    instrument and would need a different drawing.
    """
    percent = _num(_block(usage, "rateLimits", "session").get("percentUsed"))
    if percent is None:
        return None
    return min(max(percent / 100.0, 0.0), 1.0)
