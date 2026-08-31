"""Alerts fire on measured data, and say which quota they are about.

Two failures observed in the field:

  1. "Limite semanal Claude esgotado" arrived with most of the week left. The
     API had hiccuped, build_rate_limits() fell back to local_estimate, and
     that branch divides tokens by a hardcoded WEEKLY_ALL_LIMIT and clamps with
     min(100, …) — so it reads 100% for any heavy user. A guess announced an
     exhausted quota.
  2. The message never said *which* quota. weeklyAll, weeklyOpus, weeklyFable
     and weeklyScoped can all be live at once.
"""
import pytest


def _rl(source="api", **scopes):
    d = {"source": source}
    d.update(scopes)
    return {"rateLimits": d}


def _blk(pct, resets="2026-09-04T04:59:59Z", **extra):
    d = {"percentUsed": pct, "resetsAt": resets}
    d.update(extra)
    return d


def _ids(events):
    return [e["id"] for e in events]


# ── 1. an estimate must never announce anything ──

def test_local_estimate_does_not_fire_exhausted(collector):
    """The exact field failure: estimate saturates at 100 with the week young."""
    prev = {"measured": True,
            "weeklyAll": {"percentUsed": 35, "resetsAt": "2026-09-04T04:59:59Z", "fired": []}}
    events, snap = collector.detect_usage_transitions(
        prev, _rl(source="local_estimate", weeklyAll=_blk(100, "")))
    assert _ids(events) == [], f"an estimate raised alerts: {_ids(events)}"


def test_estimate_does_not_poison_the_fired_state(collector):
    """If the estimate marked thresholds as announced, the real 90% that
    follows would be silently swallowed."""
    prev = {"measured": True,
            "weeklyAll": {"percentUsed": 35, "resetsAt": "2026-09-04T04:59:59Z", "fired": []}}
    _, snap = collector.detect_usage_transitions(
        prev, _rl(source="local_estimate", weeklyAll=_blk(100, "")))
    assert snap["weeklyAll"]["fired"] == [], snap["weeklyAll"]
    events, _ = collector.detect_usage_transitions(
        snap, _rl(weeklyAll=_blk(91)))
    assert "weeklyAlert" in _ids(events), "real alert lost after an estimate blip"


def test_round_trip_through_an_estimate_keeps_thresholds_armed(collector):
    """api -> estimate -> api. The re-arm used to require both resetsAt values
    to be non-empty, so the empty one from the estimate left `fired` stuck."""
    state = {"measured": True,
             "weeklyAll": {"percentUsed": 35, "resetsAt": "2026-09-04T04:59:59Z", "fired": []}}
    _, state = collector.detect_usage_transitions(
        state, _rl(source="local_estimate", weeklyAll=_blk(100, "")))
    _, state = collector.detect_usage_transitions(state, _rl(weeklyAll=_blk(35)))
    assert state["weeklyAll"]["fired"] == [], state["weeklyAll"]
    events, _ = collector.detect_usage_transitions(state, _rl(weeklyAll=_blk(76)))
    assert "weeklyWarn" in _ids(events)


# ── 2. the message must name the quota ──

def test_event_carries_scope_and_percent(collector):
    events, _ = collector.detect_usage_transitions(
        {"measured": True, "weeklyAll": {"percentUsed": 10, "resetsAt": "2026-09-04T04:59:59Z", "fired": []}},
        _rl(weeklyAll=_blk(91)))
    assert len(events) == 1
    e = events[0]
    assert e["scope"] == "weeklyAll"
    assert "Semanal" in e["label"]
    assert e["percent"] == 91


def test_per_model_scope_is_named_by_the_api(collector):
    """weeklyScoped carries the model the API scoped; the alert should use it
    rather than a generic label."""
    events, _ = collector.detect_usage_transitions(
        {"measured": True},
        _rl(weeklyScoped=_blk(93, modelName="Fable")))
    assert events, "no event produced"
    assert events[0]["label"] == "Semanal Fable", events[0]


def test_each_weekly_model_alerts_separately(collector):
    """Opus at 92 and Fable at 20 must produce exactly one alert, about Opus."""
    events, _ = collector.detect_usage_transitions(
        {"measured": True},
        _rl(weeklyOpus=_blk(92), weeklyFable=_blk(20)))
    assert len(events) == 1, _ids(events)
    assert "Opus" in events[0]["label"]


def test_notification_text_names_the_quota(collector, monkeypatch):
    seen = {}
    monkeypatch.setattr(collector, "_play_event_sound", lambda *a, **k: None)
    monkeypatch.setattr(collector, "_notify_desktop",
                        lambda title, body, urgency, **k: seen.update(
                            title=title, body=body))
    collector.notify_usage_event(
        {"id": "weeklyAlert", "scope": "weeklyOpus",
         "label": "Semanal Opus", "percent": 92.0}, {})
    assert "Semanal Opus" in seen["title"], seen
    assert "92%" in seen["body"], seen
    assert "esgotad" not in seen["title"].lower(), "an alert must not read as exhausted"


def test_plain_string_event_still_works(collector, monkeypatch):
    """Backward compatibility for any caller passing a bare id."""
    seen = {}
    monkeypatch.setattr(collector, "_play_event_sound", lambda *a, **k: None)
    monkeypatch.setattr(collector, "_notify_desktop",
                        lambda title, body, urgency, **k: seen.update(title=title))
    collector.notify_usage_event("weeklyEnded", {})
    assert seen["title"]


@pytest.mark.parametrize("event_id", ["sessionEnded", "sessionReset", "weeklyEnded",
                                      "weeklyReset", "sessionWarn", "sessionAlert",
                                      "weeklyWarn", "weeklyAlert"])
def test_every_event_has_a_headline(collector, event_id):
    assert collector.USAGE_EVENT_DEFAULTS[event_id].get("headline"), event_id


# ── 3. sub-second noise in resetsAt must not look like a new window ──

# Three consecutive real reads of the same window, captured from the live
# endpoint on 2026-08-31. Same instant, different fraction every time.
NOISY_WINDOW = [
    "2026-09-04T04:59:59.340221+00:00",
    "2026-09-04T04:59:59.087415+00:00",
    "2026-09-04T04:59:59.884651+00:00",
]


def test_subsecond_noise_is_not_a_new_window(collector):
    """Comparing raw strings makes every 30s poll look like a fresh window,
    which re-arms the thresholds and turns one alert into a stream."""
    ids = {collector._window_id(v) for v in NOISY_WINDOW}
    assert len(ids) == 1, f"same window read as {len(ids)} different windows: {ids}"


def test_threshold_does_not_repeat_across_noisy_polls(collector):
    """The behaviour that noise would break, end to end."""
    state = {"measured": True,
             "weeklyAll": {"percentUsed": 70, "resetsAt": NOISY_WINDOW[0], "fired": []}}
    total = 0
    for i, reset in enumerate(NOISY_WINDOW * 4):
        events, state = collector.detect_usage_transitions(
            state, _rl(weeklyAll=_blk(80 + i * 0.1, reset)))
        total += _ids(events).count("weeklyWarn")
    assert total == 1, f"weeklyWarn fired {total} times inside one window"


def test_a_real_rollover_is_still_detected(collector):
    """The fix must not blind the detector to an actual new window."""
    state = {"measured": True,
             "weeklyAll": {"percentUsed": 80, "resetsAt": NOISY_WINDOW[0],
                           "fired": [collector.USAGE_WARN_AT]}}
    _, state = collector.detect_usage_transitions(
        state, _rl(weeklyAll=_blk(4, "2026-09-11T04:59:59.111111+00:00")))
    assert state["weeklyAll"]["fired"] == [], "next window did not re-arm"
    events, _ = collector.detect_usage_transitions(
        state, _rl(weeklyAll=_blk(77, "2026-09-11T04:59:59.222222+00:00")))
    assert "weeklyWarn" in _ids(events)
