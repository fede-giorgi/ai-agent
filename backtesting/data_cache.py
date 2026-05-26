"""Point-in-time data cache: download the full backtest window ONCE, persist it,
and serve raw (un-masked) reads.

The cache holds the *entire* window — including prices after any given cutoff —
because it is downloaded once and is "the truth" the harness marks-to-market
against. Agent-facing reads never touch this directly; they go through
``AsOfProvider`` (as_of_provider.py), which masks everything to ``≤ cutoff``.

``build()`` reuses the existing ``tools/`` functions so the API parsing stays in
one place; it fetches each ticker's endpoints concurrently and the line-items
endpoint for the whole universe in a single POST. Results persist to JSON with a
manifest so re-runs with the same (universe, window) make zero API calls.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from . import config

# Endpoint keys used in the store.
ENDPOINTS = ("prices", "financials", "metrics", "line_items",
             "news", "insider", "analyst", "segmented")


class PiTDataCache:
    """Full-window cache of FinancialDatasets responses, keyed by (ticker, endpoint)."""

    def __init__(self, universe: list[str], start: str, end: str,
                 cache_dir: str = config.CACHE_DIR):
        self.universe = sorted(set(universe))
        self.start = start
        self.end = end
        self.cache_dir = cache_dir
        # store[ticker][endpoint] -> tool-shaped dict for the full window
        self.store: dict[str, dict[str, dict]] = {}

    # ── construction ────────────────────────────────────────────────────────

    @classmethod
    def from_store(cls, store: dict, universe: list[str], start: str, end: str) -> "PiTDataCache":
        """Build a cache directly from an in-memory store (used by tests — no I/O)."""
        c = cls(universe, start, end)
        c.store = store
        return c

    @property
    def _manifest(self) -> dict:
        return {"universe": self.universe, "start": self.start, "end": self.end}

    def _paths(self):
        return (os.path.join(self.cache_dir, "manifest.json"),
                os.path.join(self.cache_dir, "data.json"))

    def build(self, *, force: bool = False, log=print) -> "PiTDataCache":
        """Download the full window once (concurrently) and persist. Idempotent:
        if a matching manifest is already on disk and ``force`` is False, load it."""
        man_path, data_path = self._paths()
        if not force and os.path.exists(man_path) and os.path.exists(data_path):
            try:
                with open(man_path) as f:
                    if json.load(f) == self._manifest:
                        with open(data_path) as df:
                            self.store = json.load(df)
                        log(f"[cache] hit — loaded {len(self.store)} tickers from {self.cache_dir}")
                        return self
            except (OSError, json.JSONDecodeError):
                pass

        log(f"[cache] building for {len(self.universe)} tickers {self.start}..{self.end}")
        tickers = list(self.universe)
        price_tickers = sorted(set(tickers) | {config.SPY_TICKER})
        self.store = {t: {} for t in price_tickers}

        # Per-ticker endpoints fetched concurrently.
        with ThreadPoolExecutor(max_workers=config.MAX_FETCH_WORKERS) as pool:
            futs = {pool.submit(self._fetch_ticker, t): t for t in price_tickers}
            for fut in as_completed(futs):
                t = futs[fut]
                try:
                    self.store[t].update(fut.result())
                except Exception as e:  # noqa: BLE001 — never let one ticker kill the build
                    log(f"[cache] {t}: fetch error: {e}")

        # Line items: one POST for the whole universe, then split by ticker.
        self._fetch_line_items(log)

        os.makedirs(self.cache_dir, exist_ok=True)
        with open(man_path, "w") as f:
            json.dump(self._manifest, f)
        with open(data_path, "w") as f:
            json.dump(self.store, f)
        log(f"[cache] built and persisted to {self.cache_dir}")
        return self

    def _fetch_ticker(self, ticker: str) -> dict[str, dict]:
        """Fetch every per-ticker endpoint for one ticker (runs in a worker thread)."""
        from tools.get_stock_prices import get_stock_prices
        from tools.get_financials import get_financials
        from tools.get_metrics import get_metrics
        from tools.get_company_news import get_company_news
        from tools.get_insider_trades import get_insider_trades
        from tools.get_analyst_estimates import get_analyst_estimates
        from tools.get_segmented_revenues import get_segmented_revenues

        lead_in = (datetime.strptime(self.start, "%Y-%m-%d")
                   - timedelta(days=config.PRICE_LEAD_IN_DAYS)).strftime("%Y-%m-%d")
        out: dict[str, dict] = {}

        def _safe(fn, key):
            try:
                out[key] = fn()
            except Exception as e:  # noqa: BLE001
                out[key] = {"error": str(e)}

        _safe(lambda: get_stock_prices.func(ticker=ticker, start_date=lead_in,
                                            end_date=self.end, interval="day"), "prices")
        # SPY only needs prices.
        if ticker == config.SPY_TICKER:
            return out
        _safe(lambda: get_financials.func(ticker=ticker, period="annual",
                                          limit=config.FINANCIALS_LIMIT, end_date=self.end), "financials")
        _safe(lambda: get_metrics.func(ticker=ticker, period="annual",
                                       limit=config.METRICS_LIMIT, end_date=self.end), "metrics")
        _safe(lambda: get_company_news.func(ticker=ticker, limit=config.NEWS_LIMIT), "news")
        _safe(lambda: get_insider_trades.func(ticker=ticker, limit=config.INSIDER_LIMIT,
                                              end_date=self.end), "insider")
        _safe(lambda: get_analyst_estimates.func(ticker=ticker, limit=config.ESTIMATES_LIMIT), "analyst")
        _safe(lambda: get_segmented_revenues.func(ticker=ticker, limit=config.SEGMENTED_LIMIT,
                                                  end_date=self.end), "segmented")
        return out

    def _fetch_line_items(self, log=print) -> None:
        """One batch POST for the whole universe; split ``search_results`` by ticker."""
        from tools.get_financial_line_items import get_financial_line_items
        try:
            res = get_financial_line_items.func(
                tickers=self.universe, line_items=config.DEFAULT_LINE_ITEMS,
                period="annual", limit=config.LINE_ITEMS_LIMIT, end_date=self.end,
            )
        except Exception as e:  # noqa: BLE001
            log(f"[cache] line_items batch error: {e}")
            return
        results = res.get("search_results", []) if isinstance(res, dict) else []
        for t in self.universe:
            self.store.setdefault(t, {})
            rows = [r for r in results if str(r.get("ticker", "")).upper() == t.upper()]
            # If the API didn't tag rows with a ticker, fall back to the full list.
            self.store[t]["line_items"] = {"search_results": rows if rows else results}

    # ── raw accessors (un-masked; used by AsOfProvider and the harness truth path) ──

    def raw(self, ticker: str, endpoint: str) -> dict:
        return (self.store.get(ticker, {}) or {}).get(endpoint, {}) or {}

    def prices(self, ticker: str) -> list[dict]:
        return self.raw(ticker, "prices").get("prices", []) or []

    def close_on(self, ticker: str, date: str) -> float | None:
        """Most recent close at or before ``date`` (forward-fills gaps/holidays)."""
        best = None
        for p in self.prices(ticker):
            t = p.get("time", "")
            if t and t <= date:
                best = p.get("close")
        return best

    def open_on(self, ticker: str, date: str) -> float | None:
        """Open exactly on ``date`` (used for next-open fills); None if not a session."""
        for p in self.prices(ticker):
            if p.get("time") == date:
                return p.get("open")
        return None

    def all_trading_dates(self) -> list[str]:
        """Sorted union of price dates across the universe ∪ SPY (the trading calendar)."""
        dates: set[str] = set()
        for t in self.store:
            for p in self.prices(t):
                if p.get("time"):
                    dates.add(p["time"])
        return sorted(dates)
