"""Smoke tests for charting (backtesting/plots.py) — renders to a temp PNG, no display.

Run: .venv/bin/python -m pytest tests/test_plots.py -q
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting.plots import ascii_sparkline, save_report_chart  # noqa: E402
from backtesting.schema import BacktestReport  # noqa: E402


def _report():
    agent = [("2026-01-05", 1000.0), ("2026-01-06", 1010.0), ("2026-01-07", 1025.0)]
    bench = {
        "1/N Equal-Weight": [("2026-01-05", 1000.0), ("2026-01-06", 1005.0), ("2026-01-07", 1008.0)],
        "S&P 500 (SPY)": [("2026-01-05", 1000.0), ("2026-01-06", 1002.0), ("2026-01-07", 1004.0)],
        "Risk-Free": [("2026-01-05", 1000.0), ("2026-01-06", 1000.1), ("2026-01-07", 1000.2)],
    }
    return BacktestReport(agent_curve=agent, benchmark_curves=bench, day_results=[], metrics={})


def test_ascii_sparkline_nonempty():
    s = ascii_sparkline([1, 2, 3, 2, 5, 4])
    assert s and len(s) == 6


def test_save_report_chart_writes_png(tmp_path):
    path = save_report_chart(_report(), path=str(tmp_path / "bt.png"))
    assert path is not None and os.path.exists(path) and os.path.getsize(path) > 0


def test_chart_short_curve_returns_none():
    short = BacktestReport(agent_curve=[("2026-01-05", 1000.0)], benchmark_curves={},
                           day_results=[], metrics={})
    assert save_report_chart(short, path=str("unused.png")) is None
