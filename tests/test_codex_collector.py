"""Behavioural tests for the Codex collector.

They pin the three things the plasmoid depends on: the percentage
normalisation, the window-by-duration choice, and the output contract the
QML reads (including the fields it must NOT emit).
"""
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

COLLECTOR = Path(__file__).resolve().parents[1] / "scripts" / "codex-usage-collector.py"


@pytest.fixture(scope="module")
def collector():
    spec = importlib.util.spec_from_file_location("codex_usage_collector", COLLECTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NOW = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)


def test_fraction_used_percent_becomes_percentage(collector):
    """Codex reports 0.53 for 53%; the bars are drawn on a 0-100 scale."""
    block = collector.rate_block({"used_percent": 0.53, "window_minutes": 300}, NOW)
    assert block["percentUsed"] == pytest.approx(53.0)


def test_percentage_used_percent_is_kept(collector):
    """A future API switch to 53 must not become 5300%."""
    block = collector.rate_block({"used_percent": 53, "window_minutes": 300}, NOW)
    assert block["percentUsed"] == pytest.approx(53.0)


def test_used_percent_is_clamped_to_the_bar_range(collector):
    assert collector.rate_block({"used_percent": 140, "window_minutes": 300}, NOW)["percentUsed"] == 100
    assert collector.rate_block({"used_percent": -3, "window_minutes": 300}, NOW)["percentUsed"] == 0


def test_resets_in_seconds_never_goes_negative(collector):
    past = (NOW - timedelta(hours=1)).timestamp()
    block = collector.rate_block({"used_percent": 0.1, "window_minutes": 300, "resets_at": past}, NOW)
    assert block["resetsInSeconds"] == 0


def test_rate_limit_blocks_are_found_in_both_spellings(collector):
    payload = {"outer": {"windows": [
        {"used_percent": 0.1, "window_minutes": 300},
        {"usedPercent": 0.2, "windowMinutes": 10080},
        {"used_percent": 0.3, "limit_window_seconds": 3600},
        {"not_a_window": True},
    ]}}
    assert len(collector.find_rate_limit_blocks(payload)) == 3


def _run_offline(collector, monkeypatch, tmp_path, remote_usage):
    monkeypatch.setattr(collector, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(collector, "fetch_authenticated_usage",
                        lambda: ({"usage": remote_usage} if remote_usage else {}, {}))
    return collector.collect()


def test_shortest_window_is_the_session_and_longest_is_the_weekly(collector, monkeypatch, tmp_path):
    """Windows are chosen by duration, so reordering the API response is harmless."""
    remote = {"rate_limit": {"blocks": [
        {"used_percent": 0.08, "window_minutes": 10080},   # weekly, listed first
        {"used_percent": 0.53, "window_minutes": 300},     # 5h
    ]}}
    data = _run_offline(collector, monkeypatch, tmp_path, remote)
    assert data["rateLimits"]["session"]["percentUsed"] == pytest.approx(53.0)
    assert data["rateLimits"]["weeklyAll"]["percentUsed"] == pytest.approx(8.0)
    assert data["rateLimits"]["source"] == "api"


def test_widget_contract_fields_are_present(collector, monkeypatch, tmp_path):
    remote = {"rate_limit": {"blocks": [{"used_percent": 0.5, "window_minutes": 300}]}, "plan_type": "plus"}
    data = _run_offline(collector, monkeypatch, tmp_path, remote)
    for key in ("percentUsed", "resetsAt", "resetsInMinutes", "resetsLabel"):
        assert key in data["rateLimits"]["session"], key
    assert data["rateLimits"]["plan"] == "plus"
    assert len(data["activity"]["daily"]) == 7
    assert json.dumps(data)  # the widget parses stdout as JSON


def test_no_per_model_weekly_windows_are_faked(collector, monkeypatch, tmp_path):
    """main.qml hides the Sonnet/Opus rows by absence; emitting them as 0 would
    draw two empty bars in Codex mode."""
    remote = {"rate_limit": {"blocks": [{"used_percent": 0.5, "window_minutes": 300}]}}
    data = _run_offline(collector, monkeypatch, tmp_path, remote)
    assert "weeklySonnet" not in data["rateLimits"]
    assert "weeklyOpus" not in data["rateLimits"]


def test_claude_only_metrics_are_not_fabricated(collector, monkeypatch, tmp_path):
    """main.qml hides a panel when its field is absent. Emitting an inert
    placeholder instead would render 'Healthy', 'Smart' or '0/h' for metrics
    the Codex collector never measured."""
    remote = {"rate_limit": {"blocks": [{"used_percent": 0.5, "window_minutes": 300}]}}
    data = _run_offline(collector, monkeypatch, tmp_path, remote)
    for key in ("dumbness", "serviceStatus", "performance", "burnRate",
                "errorRate", "adaptiveThinking", "toolUse", "costProjection"):
        assert key not in data, key


def test_local_log_is_the_fallback_when_the_api_is_unreachable(collector, monkeypatch, tmp_path):
    sessions = tmp_path / "sessions" / "2026" / "01"
    sessions.mkdir(parents=True)
    # Inside the collector's rolling 7-day window, which is anchored on the
    # real clock, so the fixture has to be anchored there too.
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    stamp = recent.isoformat().replace("+00:00", "Z")
    lines = [
        {"timestamp": stamp, "type": "session_meta", "payload": {"session_id": "s-1"}},
        {"timestamp": stamp, "type": "event_msg", "payload": {
            "type": "token_count",
            "info": {"last_token_usage": {"total_tokens": 1200},
                     "total_token_usage": {"total_tokens": 5000}},
            "rate_limits": {"primary": {"used_percent": 0.42, "window_minutes": 300},
                            "secondary": {"used_percent": 0.11, "window_minutes": 10080}}}},
    ]
    (sessions / "rollout.jsonl").write_text("\n".join(json.dumps(x) for x in lines))
    monkeypatch.setattr(collector, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(collector, "fetch_authenticated_usage", lambda: ({}, {"usage": "URLError"}))
    data = collector.collect()
    assert data["rateLimits"]["source"] == "local_log"
    assert data["rateLimits"]["session"]["percentUsed"] == pytest.approx(42.0)
    assert data["activity"]["currentThreadTokens"] == 5000
    assert data["activity"]["last7DaysSessions"] == 1
