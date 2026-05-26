"""Typed containers for walk-forward results."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DayResult:
    """One trading session in the walk-forward."""
    date: str
    ran_pipeline: bool                 # False if the skip-gate skipped this day
    reason: str                        # gate reason ("first_day", "price_move:NVDA", "no_trigger", ...)
    trades: list[dict] = field(default_factory=list)   # executed fills
    portfolio: dict[str, int] = field(default_factory=dict)
    cash: float = 0.0
    equity: float = 0.0                # mark-to-market: cash + Σ shares·close(date)
    iterations: int = 0                # debate rounds used (0 when skipped)


@dataclass
class BacktestReport:
    """Final walk-forward output: the agent curve, benchmark curves, per-day log, metrics."""
    agent_curve: list[tuple[str, float]]
    benchmark_curves: dict[str, list[tuple[str, float]]]
    day_results: list[DayResult]
    metrics: dict
