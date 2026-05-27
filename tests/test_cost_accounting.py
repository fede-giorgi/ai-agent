"""Per-tier cost accounting (llm._UsageAggregator).

Regression for the bug where a tiered run (Haiku workhorse + Sonnet judge) was
priced entirely at whichever model was created last — in practice Sonnet, the
last call each day — over-stating the bill and tripping --max-cost early.
"""

from llm import _COST_PER_1M, _UsageAggregator, _rates_for

HAIKU = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
SONNET = "us.anthropic.claude-sonnet-4-6"


def test_rates_resolve_by_longest_substring():
    assert _rates_for(HAIKU) is _COST_PER_1M["claude-haiku-4-5"]
    assert _rates_for(SONNET) is _COST_PER_1M["claude-sonnet-4-6"]
    assert _rates_for(None) is None
    assert _rates_for("totally-unknown-model") is None


def test_mixed_tiers_are_priced_per_tier():
    agg = _UsageAggregator()
    agg.record(HAIKU, 1_000_000, 1_000_000)
    agg.record(SONNET, 1_000_000, 1_000_000)
    s = agg.summary()

    h, so = _COST_PER_1M["claude-haiku-4-5"], _COST_PER_1M["claude-sonnet-4-6"]
    expected = h["input"] + h["output"] + so["input"] + so["output"]
    assert abs(s["estimated_cost_usd"] - expected) < 1e-9
    assert s["input_tokens"] == 2_000_000
    assert s["output_tokens"] == 2_000_000
    assert s["calls"] == 2


def test_haiku_heavy_run_costs_less_than_all_sonnet():
    """The old code priced this all at Sonnet; the fix must come in cheaper."""
    agg = _UsageAggregator()
    agg.record(HAIKU, 1_000_000, 1_000_000)
    s = agg.summary()

    so = _COST_PER_1M["claude-sonnet-4-6"]
    all_at_sonnet = so["input"] + so["output"]
    assert s["estimated_cost_usd"] < all_at_sonnet


def test_unknown_model_yields_no_cost():
    agg = _UsageAggregator()
    agg.record("mystery-model", 100, 100)
    s = agg.summary()
    assert s["estimated_cost_usd"] is None
    assert s["input_tokens"] == 100  # tokens still counted even when unpriced


def test_by_model_breakdown_is_exposed():
    agg = _UsageAggregator()
    agg.record(HAIKU, 10, 20)
    agg.record(HAIKU, 5, 5)
    agg.record(SONNET, 1, 2)
    by = agg.summary()["by_model"]
    assert by[HAIKU] == {"input": 15, "output": 25, "calls": 2}
    assert by[SONNET] == {"input": 1, "output": 2, "calls": 1}
