"""Benchmark equity curves over the walk-forward window.

All priced from the cache truth and aligned to the same sessions as the agent:
  - **1/N equal-weight buy-and-hold** — DeMiguel et al. (2009)'s stubborn baseline.
  - **S&P 500 (SPY) buy-and-hold**.
  - **Risk-free accrual** — cash compounding at ``RISK_FREE_ANNUAL``.
"""

from __future__ import annotations

import math
from datetime import datetime

from . import config
from .data_cache import PiTDataCache

Curve = list[tuple[str, float]]


def _shares(alloc: float, price: float, fractional: bool) -> float:
    if price <= 0:
        return 0.0
    raw = alloc / price
    return raw if fractional else math.floor(raw)


def _buy_and_hold(cache: PiTDataCache, tickers: list[str], sessions: list[str],
                  capital: float, fractional: bool) -> Curve:
    """Allocate ``capital`` equally across ``tickers`` at sessions[0], hold."""
    if not sessions:
        return []
    day0 = sessions[0]
    valid = [t for t in tickers if (cache.close_on(t, day0) or 0) > 0]
    if not valid:
        return [(d, capital) for d in sessions]
    alloc = capital / len(valid)
    holdings = {t: _shares(alloc, cache.close_on(t, day0), fractional) for t in valid}
    invested = sum(holdings[t] * cache.close_on(t, day0) for t in valid)
    leftover = capital - invested
    curve: Curve = []
    for d in sessions:
        eq = leftover + sum(sh * (cache.close_on(t, d) or 0) for t, sh in holdings.items())
        curve.append((d, eq))
    return curve


def build_benchmarks(cache: PiTDataCache, universe: list[str], sessions: list[str],
                     capital: float = config.INITIAL_CAPITAL,
                     fractional: bool = config.FRACTIONAL_SHARES) -> dict[str, Curve]:
    curves: dict[str, Curve] = {}
    curves["1/N Equal-Weight"] = _buy_and_hold(cache, universe, sessions, capital, fractional)
    curves["S&P 500 (SPY)"] = _buy_and_hold(cache, [config.SPY_TICKER], sessions, capital, fractional)

    # Risk-free: linear accrual from day 0.
    if sessions:
        d0 = datetime.strptime(sessions[0], "%Y-%m-%d")
        rf: Curve = []
        for d in sessions:
            days = (datetime.strptime(d, "%Y-%m-%d") - d0).days
            rf.append((d, capital * (1 + config.RISK_FREE_ANNUAL * days / 365.0)))
        curves["Risk-Free"] = rf
    return curves
