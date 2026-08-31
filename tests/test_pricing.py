"""The pricing table has to know the models actually in the logs.

It priced Opus 4.6 at $15/$75 — three times the current $5/$25 — and stopped at
the 4.x family, so an account running claude-opus-5 reported $0.00 spent today
next to a five-figure lifetime total computed at inflated rates.
"""
import pytest


# From the claude-api skill's cached model table (2026-06-24). Cache columns
# follow its prompt-caching reference: read ~0.1x input, write ~1.25x.
EXPECTED = {
    "claude-fable-5":   (10.00, 50.00),
    "claude-opus-5":    (5.00, 25.00),
    "claude-opus-4-8":  (5.00, 25.00),
    "claude-opus-4-7":  (5.00, 25.00),
    "claude-opus-4-6":  (5.00, 25.00),
    "claude-sonnet-5":  (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


@pytest.mark.parametrize("model,expected", sorted(EXPECTED.items()))
def test_current_models_are_priced(collector, model, expected):
    p = collector.price_for(model)
    assert p is not None, f"{model} is not priced; its traffic silently costs 0"
    assert (p["input"], p["output"]) == expected, p


@pytest.mark.parametrize("model", sorted(EXPECTED))
def test_cache_columns_follow_the_documented_multipliers(collector, model):
    p = collector.price_for(model)
    assert p["cache_read"] == pytest.approx(p["input"] * 0.10)
    assert p["cache_create"] == pytest.approx(p["input"] * 1.25)


@pytest.mark.parametrize("model", [
    "claude-opus-5[1m]",
    "claude-opus-5-20260101",
    "claude-sonnet-5[1m]",
])
def test_suffixed_ids_still_price(collector, model):
    """Model ids grow suffixes. An exact-match table prices those at zero."""
    p = collector.price_for(model)
    assert p is not None, f"{model} fell through to no price"
    assert p["input"] > 0


def test_longest_prefix_wins(collector):
    """A dated snapshot must not be captured by a shorter family prefix with
    different pricing."""
    assert collector.price_for("claude-sonnet-4-5-20250929")["input"] == 3.00


def test_unknown_model_is_recorded_not_silently_zero(collector):
    """Zero because we do not know the model is a different fact from zero
    because nothing was spent."""
    collector.UNPRICED_MODELS.clear()
    cost = collector.calculate_cost("some-future-model", 1000, 1000, 0, 0)
    assert cost == 0.0
    assert collector.UNPRICED_MODELS.get("some-future-model") == 2000


def test_zero_tokens_does_not_register_as_unpriced(collector):
    collector.UNPRICED_MODELS.clear()
    collector.calculate_cost("some-future-model", 0, 0, 0, 0)
    assert collector.UNPRICED_MODELS == {}


def test_a_real_opus5_day_costs_something(collector):
    """The regression in one line: this used to be exactly 0.00."""
    cost = collector.calculate_cost("claude-opus-5",
                                    input_t=13413, output_t=3902917,
                                    cache_read_t=1747919557,
                                    cache_create_t=29279455)
    assert cost > 0, "an Opus 5 day still prices at zero"
