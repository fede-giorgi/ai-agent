"""Tests for the deterministic research mapper (ai_agents/research_data.py).
Offline: synthetic endpoint responses, no network, no LLM.

Run: .venv/bin/python -m pytest tests/test_research_data.py -q
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_agents.research_data import build_financial_summary  # noqa: E402

PRICES = {"prices": [{"time": "2026-01-01", "close": 100.0}, {"time": "2026-03-01", "close": 120.0}]}
METRICS = {"financial_metrics": [
    {"report_period": "2025-12-31", "return_on_equity": 0.30, "operating_margin": 0.25,
     "price_to_earnings_ratio": 20.0, "market_cap": 1.0e9},
    {"report_period": "2024-12-31", "return_on_equity": 0.28, "operating_margin": 0.22},
]}
LINE_ITEMS = {"search_results": [
    {"report_period": "2025-12-31", "net_income": 200.0, "revenue": 1000.0, "gross_profit": 400.0,
     "shareholders_equity": 500.0, "outstanding_shares": 50.0,
     "issuance_or_purchase_of_equity_shares": -10.0, "total_assets": 900.0},
    {"report_period": "2024-12-31", "net_income": 180.0, "revenue": 900.0, "gross_profit": 360.0},
]}
NEWS = {"news": [{"date": "2026-02-01", "title": "Earnings beat", "source": "WSJ"}]}
SEGMENTED = {"segmented_revenues": [
    {"report_period": "2025-12-31", "items": [{"segments": {"iPhone": 2.0e9, "Services": 0.85e9}}]}]}
INSIDER = {"insider_trades": [
    {"transaction_value": 1000.0}, {"transaction_value": -500.0}, {"transaction_value": 2000.0}]}
ANALYST = {"analyst_estimates": [
    {"fiscal_period": "FY2027", "revenue": 1200.0, "earnings_per_share": 5.0}]}


def _summary():
    return build_financial_summary(
        "AAPL", prices=PRICES, metrics=METRICS, line_items=LINE_ITEMS, news=NEWS,
        segmented=SEGMENTED, insider=INSIDER, analyst=ANALYST)


def test_price_is_latest_close():
    assert _summary().price == 120.0


def test_metrics_auto_mapped():
    s = _summary()
    assert s.return_on_equity == 0.30 and s.operating_margin == 0.25
    assert s.price_to_earnings_ratio == 20.0 and s.market_cap == 1.0e9


def test_line_items_latest_and_history():
    s = _summary()
    assert s.net_income == 200.0 and s.revenue == 1000.0
    assert s.historical_net_income == [200.0, 180.0]      # most-recent first
    assert s.historical_revenue == [1000.0, 900.0]


def test_historical_metrics_from_metric_periods():
    s = _summary()
    assert s.historical_return_on_equity == [0.30, 0.28]
    assert s.historical_operating_margin == [0.25, 0.22]


def test_news_formatted():
    assert _summary().recent_news == "[2026-02-01] Earnings beat (WSJ)"


def test_segmented_flattened():
    assert _summary().segmented_revenue == {"iPhone": 2.0e9, "Services": 0.85e9}


def test_insider_aggregation():
    s = _summary()
    assert s.net_insider_buying == 2500.0
    assert s.insider_buy_count == 2 and s.insider_sell_count == 1


def test_analyst_estimate():
    s = _summary()
    assert s.analyst_revenue_estimate == 1200.0 and s.analyst_eps_estimate == 5.0
    assert s.analyst_estimate_period == "FY2027"


def test_empty_inputs_safe():
    s = build_financial_summary("X", prices={}, metrics={}, line_items={}, news={},
                                segmented={}, insider={}, analyst={})
    assert s.ticker == "X" and s.price is None and s.net_insider_buying is None


def test_run_analyses_returns_eight_blocks():
    from ai_agents.warren_buffet_agent import run_analyses
    out = run_analyses(_summary())
    assert set(out) == {"fundamentals", "consistency", "moat", "management_quality",
                        "book_value_growth", "pricing_power", "intrinsic_value", "qualitative_signals"}
