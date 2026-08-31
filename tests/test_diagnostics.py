"""Diagnostics, not vanity.

The card these replace showed "1.9B tokens / $1,442 extracted", of which 98%
was cache reads — the same context re-read, billed at a tenth of input
precisely because it is cheap. Calling that extracted value inflated the number
with an implementation detail and answered no question anyone had.
"""
import pytest


# Real proportions from this machine: 98.4% of the traffic is cache reads.
REAL_DAY = dict(inp=16_903, out=5_072_569,
                cache_read=2_393_929_541, cache_create=34_119_412)


def test_cache_savings_are_the_defensible_number(collector):
    """Cache reads bill at ~0.1x input, so the same prefix uncached costs
    roughly ten times more. That difference is worth something; the raw total
    is not."""
    e = collector.compute_efficiency(**REAL_DAY)
    assert e["uncachedUSD"] > e["costUSD"] * 5, e
    assert e["savedUSD"] == pytest.approx(e["uncachedUSD"] - e["costUSD"], abs=0.01)
    assert 0.8 < e["savedShare"] < 0.95, e["savedShare"]


def test_cache_hit_rate_is_a_share_of_reads_not_of_everything(collector):
    """Output is produced, not read; including it in the denominator would
    make the rate drift with verbosity rather than with cache behaviour."""
    e = collector.compute_efficiency(inp=100, out=1_000_000,
                                     cache_read=900, cache_create=0)
    assert e["cacheHitRate"] == pytest.approx(0.9, abs=0.001)


def test_read_per_output_flags_context_carried_for_nothing(collector):
    e = collector.compute_efficiency(**REAL_DAY)
    assert e["readPerOutput"] > 100, e["readPerOutput"]
    lean = collector.compute_efficiency(inp=1000, out=1000, cache_read=0, cache_create=0)
    assert lean["readPerOutput"] == 1.0


def test_no_output_does_not_divide_by_zero(collector):
    e = collector.compute_efficiency(inp=10, out=0, cache_read=10, cache_create=0)
    assert e["readPerOutput"] == 0


def test_efficiency_is_empty_for_an_unpriced_model(collector):
    assert collector.compute_efficiency(1, 1, 1, 1, model="not-a-model") == {}


# ── cost per session ──

def _session(sid, out, cr, msgs=10, project="p"):
    return {"id": sid, "project": project, "messages": msgs,
            "inputTokens": 0, "outputTokens": out,
            "cacheReadTokens": cr, "cacheCreateTokens": 0}


def test_sessions_rank_by_cost(collector):
    # Ids are truncated to 8 characters (they are UUIDs in practice), so the
    # fixtures stay within that to keep the assertion about ordering.
    rows = collector.compute_session_costs([
        _session("cheap", 1000, 1000),
        _session("big", 5_000_000, 500_000_000),
        _session("middle", 100_000, 10_000_000),
    ])
    assert [r["id"] for r in rows] == ["big", "middle", "cheap"]
    assert rows[0]["costUSD"] > rows[1]["costUSD"] * 2


def test_sessions_without_tokens_are_dropped(collector):
    """Sessions carried no token counts before; an empty row is noise."""
    rows = collector.compute_session_costs([
        {"id": "a", "project": "p", "messages": 3},
        _session("b", 1000, 1000),
    ])
    assert [r["id"] for r in rows] == ["b"]


def test_session_ids_are_truncated(collector):
    rows = collector.compute_session_costs(
        [_session("68e9eb26-f760-418d-a88d-613921631721", 1000, 1000)])
    assert rows[0]["id"] == "68e9eb26"


# ── health, against the account's own baseline ──

def _trend(active_days):
    return [{"date": f"2026-08-{20+i:02d}", "tokens": 1 if i < active_days else 0}
            for i in range(7)]


def test_health_is_unknown_without_enough_history(collector):
    """A verdict from two days of data is a guess wearing a verdict's clothes."""
    h = collector.compute_health({}, {}, {}, _trend(2))
    assert h["state"] == "unknown"


def test_health_is_normal_when_nothing_is_off(collector):
    h = collector.compute_health({"avgSeconds": 10.1}, {"total": 0}, {}, _trend(6))
    assert h["state"] == "normal"
    assert h["signals"] == []


def test_errors_degrade_health(collector):
    h = collector.compute_health({}, {"total": 4}, {}, _trend(6))
    assert h["state"] == "degraded"
    assert any(s["name"] == "errors" for s in h["signals"])


def test_model_mix_drop_is_measured_against_the_account_not_a_threshold(collector):
    """A silent downgrade shows as today's Opus share falling against this
    account's own week — not against a number picked in advance."""
    fallbacks = {"week": {"opus": 800, "sonnet": 200},
                 "today": {"opus": 10, "sonnet": 90}}
    h = collector.compute_health({}, {}, fallbacks, _trend(6))
    assert any(s["name"] == "modelMix" for s in h["signals"]), h


def test_a_small_sample_does_not_trigger_model_mix(collector):
    """Three calls are not a trend."""
    fallbacks = {"week": {"opus": 800, "sonnet": 200}, "today": {"opus": 0, "sonnet": 3}}
    h = collector.compute_health({}, {}, fallbacks, _trend(6))
    assert not any(s["name"] == "modelMix" for s in h["signals"])


def test_an_account_that_never_used_opus_is_not_flagged(collector):
    fallbacks = {"week": {"opus": 5, "sonnet": 995},
                 "today": {"opus": 0, "sonnet": 100}}
    h = collector.compute_health({}, {}, fallbacks, _trend(6))
    assert not any(s["name"] == "modelMix" for s in h["signals"])
