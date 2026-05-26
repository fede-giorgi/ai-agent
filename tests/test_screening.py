"""Tests for deterministic universe screening (backtesting/screening.py).
Offline: synthetic metrics + prices, no network.

Run: .venv/bin/python -m pytest tests/test_screening.py -q
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting.data_cache import PiTDataCache  # noqa: E402
from backtesting.screening import screen_universe  # noqa: E402

CUTOFF = "2026-04-01"


def _ticker(roe, pe, p_now, p_past):
    return {
        "metrics": {"financial_metrics": [
            {"report_period": "2025-12-31", "return_on_equity": roe, "price_to_earnings_ratio": pe},
        ]},
        "prices": {"prices": [
            {"time": "2026-01-01", "close": p_past},
            {"time": CUTOFF, "close": p_now},
        ]},
    }


def _cache():
    store = {
        "GREAT": _ticker(roe=0.40, pe=10, p_now=130, p_past=100),   # high quality, cheap, up
        "GOOD": _ticker(roe=0.25, pe=18, p_now=110, p_past=100),
        "MEH": _ticker(roe=0.10, pe=30, p_now=100, p_past=100),
        "BAD": _ticker(roe=0.02, pe=80, p_now=80, p_past=100),      # weak, expensive, down
    }
    return PiTDataCache.from_store(store, list(store), "2026-01-01", CUTOFF)


def test_ranks_best_first():
    ranked = screen_universe(_cache(), ["GREAT", "GOOD", "MEH", "BAD"], CUTOFF)
    assert ranked[0] == "GREAT"
    assert ranked[-1] == "BAD"


def test_top_k_truncates():
    top2 = screen_universe(_cache(), ["GREAT", "GOOD", "MEH", "BAD"], CUTOFF, top_k=2)
    assert len(top2) == 2 and "GREAT" in top2 and "BAD" not in top2


def test_deterministic():
    c = _cache()
    a = screen_universe(c, ["GREAT", "GOOD", "MEH", "BAD"], CUTOFF, top_k=3)
    b = screen_universe(c, ["BAD", "MEH", "GOOD", "GREAT"], CUTOFF, top_k=3)  # input order shuffled
    assert a == b


def test_handles_missing_metrics():
    store = {
        "A": {"metrics": {"financial_metrics": []}, "prices": {"prices": [{"time": CUTOFF, "close": 10}]}},
        "B": {"metrics": {"financial_metrics": []}, "prices": {"prices": [{"time": CUTOFF, "close": 10}]}},
    }
    cache = PiTDataCache.from_store(store, ["A", "B"], "2026-01-01", CUTOFF)
    ranked = screen_universe(cache, ["A", "B"], CUTOFF, top_k=1)  # must not crash on all-missing
    assert len(ranked) == 1
