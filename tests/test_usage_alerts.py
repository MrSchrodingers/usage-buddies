"""Threshold alerts fire while there is still something to do about it.

The only events were at 100%, which is the point where the decision to slow
down has already been made for you. These fire at 75% and 90%, and the hard
part is not firing them again: this runs every 30 seconds, so a naive
comparison produces a toast twice a minute for hours.
"""
import pytest


def _ids(events):
    """Events carry scope and percentage now, so the message can name the quota."""
    return [e["id"] if isinstance(e, dict) else e for e in events]


def _data(session=None, weekly=None):
    # source=api: alerts only fire on measured data. The local_estimate branch
    # saturates at 100% for heavy users and used to announce an exhausted quota.
    rl = {"source": "api"}
    if session is not None:
        rl["session"] = session
    if weekly is not None:
        rl["weeklyAll"] = weekly
    return {"rateLimits": rl}


def _sess(pct, resets="2026-09-01T00:00:00Z"):
    return {"percentUsed": pct, "resetsAt": resets}


def test_warn_fires_once_when_crossing(collector):
    prev = {"measured": True, "session": {"percentUsed": 70, "resetsAt": "2026-09-01T00:00:00Z", "fired": []}}
    events, snap = collector.detect_usage_transitions(prev, _data(session=_sess(76)))
    assert "sessionWarn" in _ids(events)
    assert collector.USAGE_WARN_AT in snap["session"]["fired"]


def test_warn_does_not_repeat_every_run(collector):
    """30s timer: a threshold that re-fires is a toast twice a minute."""
    state = {"measured": True, "session": {"percentUsed": 70, "resetsAt": "2026-09-01T00:00:00Z", "fired": []}}
    fired_total = 0
    for pct in (76, 77, 78, 79, 80, 81):
        events, state = collector.detect_usage_transitions(state, _data(session=_sess(pct)))
        fired_total += _ids(events).count("sessionWarn")
    assert fired_total == 1, f"warn fired {fired_total} times across one window"


def test_alert_suppresses_warn_when_both_cross_at_once(collector):
    """Jumping straight past both thresholds must not stack two toasts saying
    the same thing."""
    prev = {"measured": True, "session": {"percentUsed": 10, "resetsAt": "2026-09-01T00:00:00Z", "fired": []}}
    events, snap = collector.detect_usage_transitions(prev, _data(session=_sess(95)))
    assert _ids(events).count("sessionAlert") == 1
    assert "sessionWarn" not in _ids(events)
    # both are recorded, so neither fires later in the same window
    assert set(snap["session"]["fired"]) == {collector.USAGE_WARN_AT, collector.USAGE_ALERT_AT}


def test_new_window_rearms_the_thresholds(collector):
    """Without re-arming, a quota warned about once is never warned about again.

    prev_pct is kept at 2 on purpose. The reset branch also clears `fired`, but
    only when the previous window had more than 5% used — with 80% there, this
    test passes even with the re-arm removed, which is how the first version of
    it proved nothing.
    """
    state = {"measured": True, "session": {"percentUsed": 2,
                         "resetsAt": "2026-09-01T00:00:00Z",
                         "fired": [collector.USAGE_WARN_AT]}}
    events, state = collector.detect_usage_transitions(
        state, _data(session=_sess(3, "2026-09-01T05:00:00Z")))
    assert "sessionReset" not in _ids(events), (
        "the reset branch fired and would clear `fired` on its own; "
        "this test would then pass without any re-arm logic"
    )
    assert state["session"]["fired"] == [], "thresholds not re-armed for the new window"
    events, state = collector.detect_usage_transitions(
        state, _data(session=_sess(78, "2026-09-01T05:00:00Z")))
    assert "sessionWarn" in _ids(events)


def test_thresholds_do_not_fire_at_or_past_100(collector):
    """sessionEnded already covers that; a warn alongside it is noise."""
    prev = {"measured": True, "session": {"percentUsed": 50, "resetsAt": "2026-09-01T00:00:00Z", "fired": []}}
    events, _ = collector.detect_usage_transitions(prev, _data(session=_sess(100)))
    assert "sessionEnded" in _ids(events)
    assert "sessionWarn" not in _ids(events) and "sessionAlert" not in events


def test_weekly_scope_has_its_own_thresholds(collector):
    prev = {"measured": True, "weeklyAll": {"percentUsed": 70, "resetsAt": "2026-09-05T00:00:00Z", "fired": []}}
    events, _ = collector.detect_usage_transitions(prev, _data(weekly=_sess(91, "2026-09-05T00:00:00Z")))
    assert "weeklyAlert" in _ids(events)


def test_every_event_id_has_defaults(collector):
    """A fired event with no defaults entry is silently dropped by
    notify_usage_event()."""
    prev = {"measured": True, "session": {"percentUsed": 10, "resetsAt": "2026-09-01T00:00:00Z", "fired": []},
            "weeklyAll": {"percentUsed": 10, "resetsAt": "2026-09-05T00:00:00Z", "fired": []}}
    events, _ = collector.detect_usage_transitions(
        prev, _data(session=_sess(95), weekly=_sess(95, "2026-09-05T00:00:00Z")))
    assert events, "no events produced; test proves nothing"
    for event_id in _ids(events):
        assert event_id in collector.USAGE_EVENT_DEFAULTS, f"{event_id} has no defaults"


@pytest.mark.parametrize("field", ["sound", "winSound", "urgency", "title", "body"])
def test_new_defaults_are_complete(collector, field):
    for event_id in ("sessionWarn", "sessionAlert", "weeklyWarn", "weeklyAlert"):
        assert collector.USAGE_EVENT_DEFAULTS[event_id].get(field), f"{event_id}.{field}"


def test_thresholds_match_what_the_widget_draws(collector):
    """The collector's alert boundaries and the plasmoid's alert zones must be
    the same numbers, or the toast and the bar disagree."""
    from pathlib import Path
    qml = (Path(__file__).resolve().parents[1] /
           "plasmoid" / "contents" / "ui" / "main.qml").read_text()
    assert f"readonly property real warnAt: {collector.USAGE_WARN_AT}" in qml
    assert f"readonly property real alertAt: {collector.USAGE_ALERT_AT}" in qml
