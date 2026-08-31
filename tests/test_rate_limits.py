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


# ── Coexistence of the legacy seven_day_* fields with the new limits[] array ──

def test_null_percent_does_not_erase_a_real_legacy_value(limits_of):
    """`percent: null` means the API has no number, not zero. Writing 0 over a
    real seven_day_sonnet reading shows "0% used" on a quota that may be spent."""
    r = limits_of([_scoped(None, "Claude Sonnet 5")],
                  seven_day_sonnet={"utilization": 87, "resets_at": "2026-09-05T04:59:00Z"})
    assert r["weeklySonnet"]["percentUsed"] == 87, (
        f"legacy value overwritten by a null percent: {r['weeklySonnet']}"
    )


def test_zero_percent_is_kept(limits_of):
    """0 is a real reading and must not be confused with null."""
    r = limits_of([_scoped(0, "Fable")])
    assert r["weeklyFable"]["percentUsed"] == 0


def test_unknown_model_wins_scoped_over_a_known_one(limits_of):
    """weeklyScoped is the only place an unrecognised model can appear, so it
    must not be spent on a model that already has its own field."""
    r = limits_of([_scoped(55, "Claude Opus 5"), _scoped(88, "Quasar")])
    assert r["weeklyOpus"]["percentUsed"] == 55
    assert r["weeklyScoped"]["modelName"] == "Quasar", (
        f"unknown model dropped; weeklyScoped went to {r['weeklyScoped']['modelName']!r}"
    )


def test_scoped_mirrors_first_when_all_known(limits_of):
    r = limits_of([_scoped(55, "Claude Opus 5"), _scoped(71, "Fable")])
    assert r["weeklyScoped"]["modelName"] == "Claude Opus 5"


@pytest.mark.parametrize("display,expected", [
    ("Claude Haiku 5 (Opus-distilled)", "weeklyHaiku"),
    ("Claude Opus 4.6 (Haiku-speed preview)", "weeklyOpus"),
    ("Corpus 1", None),
    ("Claude Sonnet 5", "weeklySonnet"),
])
def test_family_match_is_positional_not_dict_order(limits_of, display, expected):
    """Dict order must not decide which family a name belongs to: filing a Haiku
    cap under weeklyOpus would overwrite the real Opus quota."""
    r = limits_of([_scoped(42, display)])
    named = {k for k in r if k.startswith("weekly") and k not in ("weeklyAll", "weeklyScoped")}
    named = {k for k in named if r[k].get("modelName") == display}
    if expected is None:
        assert not named, f"{display!r} should match no family, matched {named}"
    else:
        assert named == {expected}, f"{display!r} -> {named}, expected {expected}"
