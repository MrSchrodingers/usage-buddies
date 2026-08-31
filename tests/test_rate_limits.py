"""The 2026 `limits[]` schema feeds two UI contracts at once.

PR #7 and PR #8 each consumed `limits[].kind == "weekly_scoped"` on their own,
in the same spot, and each dropped what the other kept:

  - PR #7 mapped N models onto rateLimits.weekly<Model>, but silently discarded
    any model missing from its hardcoded table.
  - PR #8 kept the API's own display_name in rateLimits.weeklyScoped, but had a
    `break` and so surfaced only the first entry.

Both consumers are live: the QML plasmoid binds weeklyFable (fableBarOnly mode),
win-widget/src/main.js binds weeklyScoped. These tests pin both.
"""
import pytest


def _scoped(pct, display, resets="2026-09-10T18:00:00Z"):
    return {"kind": "weekly_scoped", "percent": pct, "resets_at": resets,
            "scope": {"model": {"display_name": display}}}


def _api(limits, **extra):
    payload = {
        "limits": limits,
        "five_hour": {"utilization": 20, "resets_at": "2026-08-31T20:00:00Z"},
        "seven_day": {"utilization": 30, "resets_at": "2026-09-05T04:59:00Z"},
    }
    payload.update(extra)
    return payload


@pytest.fixture
def limits_of(collector, monkeypatch):
    def build(limits, **extra):
        monkeypatch.setattr(collector, "fetch_usage_from_api",
                            lambda *a, **k: _api(limits, **extra))
        monkeypatch.setattr(collector, "fetch_credits_from_api", lambda *a, **k: None)
        return collector.build_rate_limits()
    return build


def test_unknown_model_is_not_dropped(limits_of):
    """A model with no weekly<Model> field must still reach the UI, labelled by
    the API. Otherwise every model Anthropic adds is invisible until we ship."""
    r = limits_of([_scoped(33, "Quasar")])
    assert r.get("weeklyScoped"), "unknown model dropped entirely"
    assert r["weeklyScoped"]["modelName"] == "Quasar"
    assert r["weeklyScoped"]["percentUsed"] == 33


def test_every_known_model_gets_its_own_field(limits_of):
    """Two scoped entries in one response must yield two named blocks —
    the plasmoid binds each model's bar to a fixed key."""
    r = limits_of([_scoped(55, "Claude Opus 5"), _scoped(71, "Fable", "2026-09-11T18:00:00Z")])
    assert r["weeklyOpus"]["percentUsed"] == 55
    assert r["weeklyFable"]["percentUsed"] == 71


def test_scoped_holds_first_entry(limits_of):
    r = limits_of([_scoped(55, "Claude Opus 5"), _scoped(71, "Fable")])
    assert r["weeklyScoped"]["percentUsed"] == 55
    assert r["weeklyScoped"]["modelName"] == "Claude Opus 5"


def test_no_scoped_entry_invents_nothing(limits_of):
    r = limits_of([{"kind": "five_hour", "percent": 10}])
    assert "weeklyScoped" not in r
    assert "weeklyFable" not in r


def test_display_name_matches_bare_or_full(limits_of):
    """display_name may be the bare family or the full model name."""
    assert "weeklyFable" in limits_of([_scoped(10, "Fable")])
    assert "weeklyFable" in limits_of([_scoped(10, "Claude Fable 5")])


# ── resetsAt: producer/consumer contract for notification events ──

def test_session_and_weekly_emit_resets_at(limits_of):
    """detect_usage_transitions() compares resetsAt across runs. A scope that
    never emits it can never fire its *Reset event."""
    r = limits_of([])
    assert r["session"].get("resetsAt"), "session.resetsAt missing -> sessionReset is dead"
    assert r["weeklyAll"].get("resetsAt"), "weeklyAll.resetsAt missing -> weeklyReset is dead"


@pytest.mark.parametrize("scope,event", [("session", "sessionReset"),
                                         ("weeklyAll", "weeklyReset")])
def test_reset_event_fires_when_window_rolls_over(collector, scope, event):
    """End-to-end on the pure function: a reset window plus prior usage fires."""
    prev = {scope: {"percentUsed": 80, "resetsAt": "2026-08-31T10:00:00Z"}}
    curr = {"rateLimits": {scope: {"percentUsed": 3, "resetsAt": "2026-08-31T20:00:00Z"}}}
    events, _ = collector.detect_usage_transitions(prev, curr)
    assert event in events, f"{event} did not fire on a rolled-over window"
