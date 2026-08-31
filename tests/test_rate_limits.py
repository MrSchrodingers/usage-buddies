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
from pathlib import Path

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


def test_scoped_present_when_every_model_is_known(limits_of):
    r = limits_of([_scoped(55, "Claude Opus 5"), _scoped(71, "Fable")])
    assert r["weeklyScoped"]["modelName"] in ("Claude Opus 5", "Fable")


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


def test_scoped_is_stable_under_reordering(limits_of):
    """limits[] carries no ordering guarantee. Picking by array position made
    the bar swap model and value between refreshes with nothing to explain it."""
    a = limits_of([_scoped(55, "Claude Opus 5"), _scoped(71, "Fable")])
    b = limits_of([_scoped(71, "Fable"), _scoped(55, "Claude Opus 5")])
    assert a["weeklyScoped"] == b["weeklyScoped"]


def test_scoped_shows_the_most_used_unknown_model(limits_of):
    a = limits_of([_scoped(11, "Quasar"), _scoped(99, "Nebula")])
    b = limits_of([_scoped(99, "Nebula"), _scoped(11, "Quasar")])
    assert a["weeklyScoped"]["modelName"] == "Nebula"
    assert b["weeklyScoped"]["modelName"] == "Nebula"


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


# ── Shape observed on the live endpoint, 2026-08-31 ──
#
# Captured by calling fetch_usage_from_api() against claude.ai with a real
# session. Recorded because both PRs coded against this shape from assumption,
# not observation, and one field contradicted every synthetic payload here:
# a weekly_scoped entry can carry resets_at = None.
#
#   limits: [
#     {kind: "session",       percent: 1,  resets_at: "...+00:00", scope: {...}},
#     {kind: "weekly_all",    percent: 32, resets_at: "...+00:00", scope: {...}},
#     {kind: "weekly_scoped", percent: 0,  resets_at: None,
#      scope: {model: {id: None, display_name: "Fable"}, surface: ...}},
#   ]
#   seven_day_opus: null, seven_day_sonnet: null   (legacy fields deprecating)
#   percent is an int on 0-100, same scale as seven_day.utilization.

LIVE_LIMITS = [
    {"kind": "session", "percent": 1, "resets_at": "2026-08-31T23:30:00.920335+00:00",
     "scope": {}, "group": None, "is_active": True, "severity": None},
    {"kind": "weekly_all", "percent": 32, "resets_at": "2026-09-04T04:59:59.920362+00:00",
     "scope": {}, "group": None, "is_active": True, "severity": None},
    {"kind": "weekly_scoped", "percent": 0, "resets_at": None,
     "scope": {"model": {"id": None, "display_name": "Fable"}, "surface": None},
     "group": None, "is_active": True, "severity": None},
]


def test_live_shape_populates_both_contracts(limits_of):
    """The one scoped entry must reach the plasmoid (weeklyFable) and
    win-widget (weeklyScoped) at once — that is what the merge resolution is."""
    r = limits_of(LIVE_LIMITS, seven_day_opus=None, seven_day_sonnet=None)
    assert r["weeklyFable"]["modelName"] == "Fable"
    assert r["weeklyScoped"]["modelName"] == "Fable"
    assert r["weeklyFable"]["percentUsed"] == 0


def test_null_resets_at_does_not_crash(limits_of):
    """The live weekly_scoped entry has resets_at = None. parse_timestamp
    tolerates it; the emitted block must degrade to empty strings, not None."""
    r = limits_of(LIVE_LIMITS)
    assert r["weeklyFable"]["resetsLabel"] == ""
    assert r["weeklyFable"]["resetsAt"] == ""


def test_percent_scale_matches_utilization(limits_of):
    """percent is 0-100, like seven_day.utilization. A 0-1 scale would render
    every per-model bar at ~0% while the account is near its cap."""
    r = limits_of([_scoped(32, "Fable")],
                  seven_day={"utilization": 32, "resets_at": "2026-09-04T04:59:59+00:00"})
    assert r["weeklyFable"]["percentUsed"] == r["weeklyAll"]["percentUsed"] == 32



def test_haiku_cap_is_not_invisible(limits_of):
    """A named field with no UI consumer used to swallow the entry and switch
    off the weeklyScoped rescue, so a Haiku cap at 95% appeared nowhere."""
    r = limits_of([_scoped(95, "Claude Haiku 5")])
    assert r["weeklyHaiku"]["percentUsed"] == 95
    # the plasmoid renders weeklyHaiku via weeklyScopeOrder; assert the key the
    # QML looks up actually exists
    qml = (Path(__file__).resolve().parents[1] /
           "plasmoid" / "contents" / "ui" / "main.qml").read_text()
    assert "weeklyHaiku" in qml, "weeklyHaiku has no UI consumer; the cap is invisible"
