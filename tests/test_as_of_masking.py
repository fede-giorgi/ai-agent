"""No-look-ahead tests for the point-in-time cache (backtesting/as_of_provider.py).

The core safety property: every agent-facing read returns only records dated on
or before the cutoff (boundary inclusive), regardless of any caller end_date.
Pure / offline — uses a synthetic in-memory cache, no network.

Run: .venv/bin/python -m pytest tests/test_as_of_masking.py -q
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting.as_of_provider import AsOfProvider  # noqa: E402
from backtesting.data_cache import PiTDataCache  # noqa: E402

CUTOFF = "2026-02-01"

STORE = {
    "AAPL": {
        "prices": {"prices": [
            {"time": "2026-01-01", "open": 99, "close": 100},
            {"time": "2026-02-01", "open": 108, "close": 110},   # == cutoff (inclusive)
            {"time": "2026-03-01", "open": 118, "close": 120},   # future → must be hidden
        ]},
        "financials": {
            "income_statements": [{"report_period": "2025-12-31"}, {"report_period": "2026-03-31"}],
            "balance_sheets": [{"report_period": "2025-12-31"}],
            "cash_flow_statements": [{"report_period": "2026-06-30"}],   # all future
        },
        "metrics": {"financial_metrics": [
            {"report_period": "2025-12-31"}, {"report_period": "2026-02-01"}, {"report_period": "2026-05-01"},
        ]},
        "line_items": {"search_results": [
            {"ticker": "AAPL", "report_period": "2025-12-31"},
            {"ticker": "AAPL", "report_period": "2026-04-01"},
        ]},
        "news": {"news": [
            {"date": "2026-01-15", "title": "old"},
            {"date": "2026-02-01", "title": "on-cutoff"},
            {"date": "2026-02-20", "title": "future"},
        ]},
        "insider": {"insider_trades": [
            {"filing_date": "2026-01-10"}, {"filing_date": "2026-03-10"},
        ]},
        "analyst": {"analyst_estimates": [
            {"fiscal_period": "FY2025"}, {"fiscal_period": "FY2026"}, {"fiscal_period": "FY2027"},
        ]},
        "segmented": {"segmented_revenues": [
            {"report_period": "2025-12-31"}, {"report_period": "2026-09-30"},
        ]},
    }
}


def _cache():
    return PiTDataCache.from_store(STORE, ["AAPL"], "2026-01-01", "2026-03-31")


def _provider():
    return AsOfProvider(_cache(), CUTOFF)


# ── per-endpoint masking ─────────────────────────────────────────────────────

def test_prices_hide_future():
    rows = _provider().get_stock_prices("AAPL")["prices"]
    times = [r["time"] for r in rows]
    assert times == ["2026-01-01", "2026-02-01"]
    assert all(t <= CUTOFF for t in times)


def test_prices_ignore_caller_end_date_after_cutoff():
    # The legacy bug: a far-future end_date must NOT reveal future prices.
    rows = _provider().get_stock_prices("AAPL", end_date="2026-12-31")["prices"]
    assert all(r["time"] <= CUTOFF for r in rows)


def test_prices_respect_earlier_caller_end_date():
    rows = _provider().get_stock_prices("AAPL", end_date="2026-01-15")["prices"]
    assert [r["time"] for r in rows] == ["2026-01-01"]


def test_financials_mask_report_period():
    fin = _provider().get_financials("AAPL")
    assert [s["report_period"] for s in fin["income_statements"]] == ["2025-12-31"]
    assert "cash_flow_statements" not in fin  # all future → dropped


def test_metrics_boundary_inclusive():
    rows = _provider().get_metrics("AAPL")["financial_metrics"]
    assert [r["report_period"] for r in rows] == ["2025-12-31", "2026-02-01"]


def test_line_items_mask():
    rows = _provider().get_financial_line_items(["AAPL"], ["revenue"])["search_results"]
    assert all(r["report_period"] <= CUTOFF for r in rows)
    assert len(rows) == 1


def test_news_mask_fixes_leak():
    rows = _provider().get_company_news("AAPL")["news"]
    assert all(n["date"] <= CUTOFF for n in rows)
    assert "future" not in [n["title"] for n in rows]


def test_insider_mask_by_filing_date():
    rows = _provider().get_insider_trades("AAPL")["insider_trades"]
    assert [r["filing_date"] for r in rows] == ["2026-01-10"]


def test_segmented_mask():
    rows = _provider().get_segmented_revenues("AAPL")["segmented_revenues"]
    assert [r["report_period"] for r in rows] == ["2025-12-31"]


def test_analyst_estimates_forward_only():
    # cutoff year 2026 → keep only target periods strictly after (FY2027)
    rows = _provider().get_analyst_estimates("AAPL")["analyst_estimates"]
    assert [r["fiscal_period"] for r in rows] == ["FY2027"]


def test_no_endpoint_leaks_future_date():
    """Property: across date-bearing endpoints, nothing dated after the cutoff escapes."""
    p = _provider()
    checks = [
        (p.get_stock_prices("AAPL")["prices"], "time"),
        (p.get_metrics("AAPL")["financial_metrics"], "report_period"),
        (p.get_company_news("AAPL")["news"], "date"),
        (p.get_insider_trades("AAPL")["insider_trades"], "filing_date"),
        (p.get_segmented_revenues("AAPL")["segmented_revenues"], "report_period"),
    ]
    for rows, key in checks:
        assert all(r[key] <= CUTOFF for r in rows), (key, rows)


# ── injection seam ───────────────────────────────────────────────────────────

def test_install_cache_patches_and_restores():
    from tools.get_stock_prices import get_stock_prices
    from backtesting.tool_injection import install_cache

    original = get_stock_prices.func
    with install_cache(_provider()):
        out = get_stock_prices.func(ticker="AAPL")          # served from cache, masked
        assert all(r["time"] <= CUTOFF for r in out["prices"])
    assert get_stock_prices.func is original                # restored on exit
