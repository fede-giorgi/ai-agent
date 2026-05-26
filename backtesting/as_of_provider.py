"""As-of (point-in-time) views over the data cache.

Each method mirrors the *shape* of the matching ``tools/`` function but returns
ONLY records dated on or before ``cutoff`` — the single guarantee against
look-ahead bias. Any caller-supplied ``end_date`` is clamped to the cutoff, so a
stray ``end_date`` (or none at all, as the legacy ``main.py:594`` price call did)
can never leak the future.

The ``≤ cutoff`` predicate lives in exactly one place (``_le``) so the invariant
is trivial to audit and unit-test (see tests/test_as_of_masking.py).
"""

from __future__ import annotations

import re

from .data_cache import PiTDataCache


def _le(date_str: str | None, cutoff: str) -> bool:
    """True iff a present ``YYYY-MM-DD`` date is on or before the cutoff (inclusive)."""
    return bool(date_str) and str(date_str) <= cutoff


def _period_year(s: str | None) -> int | None:
    """Extract the 4-digit year from a fiscal-period label like 'FY2025' or '2025-Q1'."""
    if not s:
        return None
    m = re.search(r"(\d{4})", str(s))
    return int(m.group(1)) if m else None


class AsOfProvider:
    """Cutoff-masked, tool-shaped reads. Construct one per backtest day."""

    def __init__(self, cache: PiTDataCache, cutoff: str):
        self.cache = cache
        self.cutoff = cutoff
        self.cutoff_year = _period_year(cutoff)

    def _eff_end(self, end_date: str | None) -> str:
        """Effective end date = the earlier of any caller end_date and the cutoff."""
        return min(end_date, self.cutoff) if end_date else self.cutoff

    # ── prices ───────────────────────────────────────────────────────────────
    def get_stock_prices(self, ticker, start_date=None, end_date=None,
                         interval="day", interval_multiplier=1) -> dict:
        eff_end = self._eff_end(end_date)
        rows = [p for p in self.cache.prices(ticker) if _le(p.get("time"), eff_end)]
        if start_date:
            rows = [p for p in rows if p.get("time", "") >= start_date]
        return {"prices": rows}

    # ── statements ─────────────────────────────────────────────────────────
    def get_financials(self, ticker, period="annual", limit=10, end_date=None) -> dict:
        raw = self.cache.raw(ticker, "financials")
        selected: dict = {}
        for key in ("income_statements", "balance_sheets", "cash_flow_statements"):
            rows = [f for f in raw.get(key, []) if _le(f.get("report_period"), self.cutoff)]
            if rows:
                selected[key] = rows[:limit]
        return selected if selected else {"error": f"No financial data before {self.cutoff}"}

    def get_metrics(self, ticker, period="annual", limit=10, end_date=None) -> dict:
        rows = [m for m in self.cache.raw(ticker, "metrics").get("financial_metrics", [])
                if _le(m.get("report_period"), self.cutoff)]
        return {"financial_metrics": rows[:limit]} if rows else {"error": f"No data before {self.cutoff}"}

    def get_financial_line_items(self, tickers, line_items, period="annual",
                                 limit=30, end_date=None) -> dict:
        want = {str(t).upper() for t in (tickers or [])}
        out: list[dict] = []
        for t in self.cache.universe:
            if want and t.upper() not in want:
                continue
            rows = [r for r in self.cache.raw(t, "line_items").get("search_results", [])
                    if _le(r.get("report_period"), self.cutoff)]
            out.extend(rows[:limit])
        return {"search_results": out} if out else {"error": f"No line items before {self.cutoff}"}

    def get_segmented_revenues(self, ticker, period="annual", limit=4, end_date=None) -> dict:
        rows = [s for s in self.cache.raw(ticker, "segmented").get("segmented_revenues", [])
                if _le(s.get("report_period"), self.cutoff)]
        return {"segmented_revenues": rows[:limit]}

    # ── filings / news (the two legacy leaks) ────────────────────────────────
    def get_insider_trades(self, ticker, limit=20, end_date=None) -> dict:
        rows = [x for x in self.cache.raw(ticker, "insider").get("insider_trades", [])
                if _le(x.get("filing_date"), self.cutoff)]
        return {"insider_trades": rows[:limit]}

    def get_company_news(self, ticker, limit=5) -> dict:
        # The live tool has NO date filter — masking here is what fixes that leak.
        rows = [n for n in self.cache.raw(ticker, "news").get("news", [])
                if _le(n.get("date"), self.cutoff)]
        rows.sort(key=lambda n: n.get("date", ""), reverse=True)
        return {"news": rows[:limit]}

    def get_analyst_estimates(self, ticker, period="annual", limit=4, end_date=None) -> dict:
        # Estimates are forward-looking with no publish date in the API. Conservative
        # rule: keep only estimates whose TARGET period is strictly after the cutoff
        # year — these are plausibly available "as of" the cutoff and avoid leaking
        # future revisions of near-term periods. Documented approximation.
        rows = []
        for e in self.cache.raw(ticker, "analyst").get("analyst_estimates", []):
            y = _period_year(e.get("fiscal_period"))
            if y is None or self.cutoff_year is None or y > self.cutoff_year:
                rows.append(e)
        return {"analyst_estimates": rows[:limit]}
