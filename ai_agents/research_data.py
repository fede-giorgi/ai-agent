"""Deterministic research data assembly — no LLM.

The old research agent ran an LLM tool-calling loop per ticker just to orchestrate
known data fetches, then a second LLM call to parse the JSON into a typed model —
pushing the full financial JSON through the model 2-3x per ticker for zero
judgment. This module replaces all of that with plain Python: call the endpoints
(live, or the cache via install_cache), then map the responses straight into a
``FinancialSummary``. The LLM is reserved for actual judgment downstream (the
Buffett conviction, the PM debate). Field names from get_metrics / line-items map
1:1 onto FinancialSummary, so most fields auto-map by name.

Works identically in live and backtest mode: in backtest the same ``tool.func``
calls are served (masked to the cutoff) from the point-in-time cache.
"""

from __future__ import annotations

from classes.financial_summary import Error, FinancialSummary, Result, ToolStatus

# Line items the Warren Buffett analysis needs (8-year history).
REQUIRED_LINE_ITEMS = [
    "capital_expenditure", "depreciation_and_amortization", "net_income",
    "outstanding_shares", "total_assets", "total_liabilities", "shareholders_equity",
    "dividends_and_other_cash_distributions", "issuance_or_purchase_of_equity_shares",
    "gross_profit", "revenue", "free_cash_flow", "current_assets", "current_liabilities",
]

_FIELDS = set(FinancialSummary.model_fields)


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _sorted_desc(rows: list[dict], key: str = "report_period") -> list[dict]:
    return sorted([r for r in rows if isinstance(r, dict)], key=lambda r: r.get(key, ""), reverse=True)


def _hist(rows: list[dict], field: str) -> list[float] | None:
    vals = [_num(r.get(field)) for r in rows]
    vals = [v for v in vals if v is not None]
    return vals or None


def build_financial_summary(ticker: str, *, prices: dict, metrics: dict, line_items: dict,
                            news: dict, segmented: dict, insider: dict, analyst: dict) -> FinancialSummary:
    """Map raw endpoint responses into a FinancialSummary — deterministic, no LLM."""
    data: dict = {"ticker": ticker}

    # Price: most-recent close.
    plist = (prices or {}).get("prices", []) or []
    if plist:
        last = max((p for p in plist if isinstance(p, dict)), key=lambda p: p.get("time", ""), default=None)
        if last:
            data["price"] = _num(last.get("close"))

    # Metrics: latest period; auto-map every key that is a FinancialSummary field.
    mrows = _sorted_desc((metrics or {}).get("financial_metrics", []) or [])
    if mrows:
        for k, v in mrows[0].items():
            if k in _FIELDS and _num(v) is not None:
                data[k] = v
        data["historical_return_on_equity"] = _hist(mrows, "return_on_equity")
        data["historical_operating_margin"] = _hist(mrows, "operating_margin")

    # Line items: latest period (auto-map) + historical arrays (most-recent first).
    lrows = _sorted_desc((line_items or {}).get("search_results", []) or [])
    if lrows:
        for k, v in lrows[0].items():
            if k in _FIELDS and _num(v) is not None:
                data[k] = v
        data["historical_net_income"] = _hist(lrows, "net_income")
        data["historical_revenue"] = _hist(lrows, "revenue")
        data["historical_gross_profit"] = _hist(lrows, "gross_profit")
        data["historical_shareholders_equity"] = _hist(lrows, "shareholders_equity")
        data["historical_outstanding_shares"] = _hist(lrows, "outstanding_shares")
        data["historical_issuance_or_purchase_of_equity_shares"] = _hist(lrows, "issuance_or_purchase_of_equity_shares")

    # News: "[date] headline (source)" lines.
    nrows = (news or {}).get("news", []) or []
    if nrows:
        lines = [f"[{n.get('date', '')}] {n.get('title', '')} ({n.get('source', '')})"
                 for n in nrows[:6] if isinstance(n, dict)]
        if lines:
            data["recent_news"] = "\n".join(lines)

    # Segmented revenues: most-recent period flattened to {segment: amount}.
    srows = _sorted_desc((segmented or {}).get("segmented_revenues", []) or [])
    if srows:
        seg: dict[str, float] = {}
        for item in srows[0].get("items", []) or []:
            segs = item.get("segments", {}) if isinstance(item, dict) else {}
            if isinstance(segs, dict):
                for name, amt in segs.items():
                    if _num(amt) is not None:
                        seg[name] = seg.get(name, 0.0) + amt
        if seg:
            data["segmented_revenue"] = seg

    # Insider trades: net value + buy/sell counts.
    irows = (insider or {}).get("insider_trades", []) or []
    if irows:
        vals = [_num(t.get("transaction_value")) or 0.0 for t in irows if isinstance(t, dict)]
        data["net_insider_buying"] = sum(vals)
        data["insider_buy_count"] = sum(1 for v in vals if v > 0)
        data["insider_sell_count"] = sum(1 for v in vals if v < 0)

    # Analyst estimates: most-forward (first) annual period.
    arows = (analyst or {}).get("analyst_estimates", []) or []
    if arows and isinstance(arows[0], dict):
        e = arows[0]
        data["analyst_revenue_estimate"] = _num(e.get("revenue"))
        data["analyst_eps_estimate"] = _num(e.get("earnings_per_share"))
        data["analyst_estimate_period"] = e.get("fiscal_period")

    return FinancialSummary(**{k: v for k, v in data.items() if k in _FIELDS})


def _status(resp: dict) -> str:
    return "ok" if isinstance(resp, dict) and "error" not in resp and resp else "error"


def assemble_result(ticker: str, backtesting_date: str | None = None) -> Result:
    """Fetch all endpoints (live or cache-served) and assemble a Result — no LLM."""
    from tools.get_stock_prices import get_stock_prices
    from tools.get_financials import get_financials
    from tools.get_metrics import get_metrics
    from tools.get_financial_line_items import get_financial_line_items
    from tools.get_company_news import get_company_news
    from tools.get_insider_trades import get_insider_trades
    from tools.get_analyst_estimates import get_analyst_estimates
    from tools.get_segmented_revenues import get_segmented_revenues

    end = backtesting_date

    def safe(fn):
        try:
            r = fn()
            return r if isinstance(r, dict) else {"error": "non-dict response"}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    prices = safe(lambda: get_stock_prices.func(ticker=ticker, end_date=end))
    financials = safe(lambda: get_financials.func(ticker=ticker, period="annual", limit=8, end_date=end))
    metrics = safe(lambda: get_metrics.func(ticker=ticker, period="annual", limit=8, end_date=end))
    line_items = safe(lambda: get_financial_line_items.func(
        tickers=[ticker], line_items=REQUIRED_LINE_ITEMS, period="annual", limit=8, end_date=end))
    news = safe(lambda: get_company_news.func(ticker=ticker, limit=5))
    segmented = safe(lambda: get_segmented_revenues.func(ticker=ticker, period="annual", limit=4, end_date=end))
    insider = safe(lambda: get_insider_trades.func(ticker=ticker, limit=20, end_date=end))
    analyst = safe(lambda: get_analyst_estimates.func(ticker=ticker, period="annual", limit=4, end_date=end))

    summary = build_financial_summary(
        ticker, prices=prices, metrics=metrics, line_items=line_items, news=news,
        segmented=segmented, insider=insider, analyst=analyst)

    status = ToolStatus(
        get_financials=_status(financials), get_metrics=_status(metrics),
        get_financial_line_items=_status(line_items), get_stock_prices=_status(prices),
        get_company_news=_status(news), get_segmented_revenues=_status(segmented),
        get_insider_trades=_status(insider), get_analyst_estimates=_status(analyst),
    )

    notes = []
    if summary.price is None:
        notes.append("no price available at cutoff")
    errs = [Error(tool=name, message=resp["error"], ticker=ticker)
            for name, resp in {"get_metrics": metrics, "get_financial_line_items": line_items,
                               "get_stock_prices": prices}.items()
            if isinstance(resp, dict) and "error" in resp]

    return Result(ticker=ticker, financial_summary=summary, tool_status=status,
                  data_quality_notes=notes, errors=errs)
