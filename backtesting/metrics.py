"""Performance metrics over an equity curve.

An equity *curve* is a list of ``(date, equity)`` pairs in chronological order.
All functions are pure and unit-tested offline.
"""

from __future__ import annotations

import math

from . import config

Curve = list[tuple[str, float]]


def total_return(curve: Curve) -> float:
    if len(curve) < 2 or curve[0][1] == 0:
        return 0.0
    return curve[-1][1] / curve[0][1] - 1.0


def daily_returns(curve: Curve) -> list[float]:
    rets = []
    for (_, prev), (_, cur) in zip(curve, curve[1:]):
        rets.append(cur / prev - 1.0 if prev else 0.0)
    return rets


def annualized_return(curve: Curve, periods_per_year: int = config.TRADING_DAYS_PER_YEAR) -> float:
    n = len(curve) - 1
    if n <= 0 or curve[0][1] <= 0:
        return 0.0
    growth = curve[-1][1] / curve[0][1]
    if growth <= 0:
        return -1.0
    return growth ** (periods_per_year / n) - 1.0


def sharpe(curve: Curve, rf_annual: float = config.RISK_FREE_ANNUAL,
           periods_per_year: int = config.TRADING_DAYS_PER_YEAR) -> float:
    rets = daily_returns(curve)
    if len(rets) < 2:
        return 0.0
    rf_daily = rf_annual / periods_per_year
    excess = [r - rf_daily for r in rets]
    mean = sum(excess) / len(excess)
    var = sum((x - mean) ** 2 for x in excess) / (len(excess) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0
    return (mean / sd) * math.sqrt(periods_per_year)


def max_drawdown(curve: Curve) -> float:
    """Largest peak-to-trough decline as a negative fraction (e.g. -0.23)."""
    peak = float("-inf")
    mdd = 0.0
    for _, eq in curve:
        peak = max(peak, eq)
        if peak > 0:
            mdd = min(mdd, eq / peak - 1.0)
    return mdd


def alpha_vs(curve: Curve, benchmark: Curve) -> float:
    """Total-return excess of the agent over a benchmark."""
    return total_return(curve) - total_return(benchmark)


def daily_win_rate(curve: Curve, benchmark: Curve) -> float:
    """Fraction of days the agent's daily return beat the benchmark's."""
    a, b = daily_returns(curve), daily_returns(benchmark)
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    return sum(1 for i in range(n) if a[i] > b[i]) / n


def summarize(agent: Curve, benchmarks: dict[str, Curve]) -> dict:
    """All metrics for the agent plus per-benchmark comparison."""
    out = {
        "agent": {
            "total_return": total_return(agent),
            "annualized_return": annualized_return(agent),
            "sharpe": sharpe(agent),
            "max_drawdown": max_drawdown(agent),
            "final_equity": agent[-1][1] if agent else 0.0,
        },
        "benchmarks": {},
        "beaten": [],
    }
    for name, bench in benchmarks.items():
        out["benchmarks"][name] = {
            "total_return": total_return(bench),
            "sharpe": sharpe(bench),
            "max_drawdown": max_drawdown(bench),
            "alpha": alpha_vs(agent, bench),
            "daily_win_rate": daily_win_rate(agent, bench),
        }
        if alpha_vs(agent, bench) > 0:
            out["beaten"].append(name)
    out["n_benchmarks"] = len(benchmarks)
    out["n_beaten"] = len(out["beaten"])
    return out
