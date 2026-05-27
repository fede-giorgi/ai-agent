"""Order execution and mark-to-market for the walk-forward.

Mirrors the live trade semantics in ``main.py`` (integer shares, no shorting,
no fees) but is stricter: buys are clamped to affordable whole shares so cash
never goes negative. Fills use the **next session's open** by default (clean,
no look-ahead — today's close is in the decision's information set, the next
open is the first executable price), configurable to close-of-day.

Mark-to-market reads the cache *truth* (future prices allowed here — this is the
harness, never an agent input).
"""

from __future__ import annotations

import math

from . import config
from .calendar import TradingCalendar
from .data_cache import PiTDataCache


class ExecutionEngine:
    def __init__(self, cache: PiTDataCache, calendar: TradingCalendar,
                 fill_timing: str = config.FILL_TIMING,
                 slippage_bps: float = config.SLIPPAGE_BPS,
                 fractional: bool = config.FRACTIONAL_SHARES):
        self.cache = cache
        self.cal = calendar
        self.fill_timing = fill_timing
        self.slippage = slippage_bps / 10_000.0
        self.fractional = fractional

    def _base_fill_price(self, ticker: str, decision_date: str) -> float | None:
        if self.fill_timing == "close":
            return self.cache.close_on(ticker, decision_date)
        nxt = self.cal.next_session(decision_date)
        if nxt is not None:
            px = self.cache.open_on(ticker, nxt)
            if px:
                return px
        # Fallback: no next session (end of window) → use decision-day close.
        return self.cache.close_on(ticker, decision_date)

    def _shares(self, requested: float) -> float:
        return requested if self.fractional else math.floor(requested)

    def apply(self, trades: list[dict], portfolio: dict[str, int], cash: float,
              decision_date: str) -> tuple[dict, float, list[dict]]:
        """Execute target trades; return (portfolio, cash, fills)."""
        portfolio = dict(portfolio)
        fills: list[dict] = []
        for t in trades or []:
            ticker = str(t.get("ticker", "")).upper()
            action = str(t.get("action", "")).lower()
            req = t.get("shares", 0) or 0
            base = self._base_fill_price(ticker, decision_date)
            if not base or base <= 0 or req <= 0 or action not in ("buy", "sell"):
                continue
            if action == "buy":
                price = base * (1 + self.slippage)
                affordable = cash / price if price > 0 else 0
                shares = self._shares(min(req, affordable))
                if shares <= 0:
                    continue
                cash -= shares * price
                portfolio[ticker] = portfolio.get(ticker, 0) + shares
            else:  # sell
                price = base * (1 - self.slippage)
                held = portfolio.get(ticker, 0)
                shares = self._shares(min(req, held))
                if shares <= 0:
                    continue
                cash += shares * price
                portfolio[ticker] = held - shares
                if portfolio[ticker] <= 0:
                    portfolio.pop(ticker, None)
            fills.append({"action": action, "ticker": ticker,
                          "shares": shares, "fill_price": round(price, 4)})
        return portfolio, cash, fills

    def mark_to_market(self, portfolio: dict[str, int], cash: float, date: str) -> float:
        equity = cash
        for ticker, shares in portfolio.items():
            close = self.cache.close_on(ticker, date)
            if close:
                equity += shares * close
        return equity
