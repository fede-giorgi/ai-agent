"""Charts for a walk-forward BacktestReport.

Headless-safe (matplotlib 'Agg' backend) so it works over SSH / on EC2 — writes a
PNG rather than opening a window. Two panels:
  1. Equity curves: agent vs 1/N, SPY, risk-free.
  2. Cumulative outperformance vs 1/N, shaded green where the agent is ahead and
     red where behind — i.e. *when and how* we beat the benchmark.

Also a dependency-free ASCII sparkline for a quick terminal glance. If matplotlib
is not installed, ``save_report_chart`` returns None instead of raising.
"""

from __future__ import annotations

import os
from datetime import datetime

from .schema import BacktestReport

_BLOCKS = "▁▂▃▄▅▆▇█"


def ascii_sparkline(values: list[float]) -> str:
    pts = [v for v in values if v is not None]
    if len(pts) < 2:
        return ""
    lo, hi = min(pts), max(pts)
    rng = hi - lo or 1.0
    return "".join(_BLOCKS[min(len(_BLOCKS) - 1, int((v - lo) / rng * (len(_BLOCKS) - 1)))] for v in pts)


def _curve_xy(curve):
    xs = [datetime.strptime(d, "%Y-%m-%d") for d, _ in curve]
    ys = [v for _, v in curve]
    return xs, ys


def save_report_chart(report: BacktestReport, path: str | None = None,
                      out_dir: str = ".") -> str | None:
    """Render the 2-panel chart to a PNG. Returns the path, or None if matplotlib
    is unavailable / the curve is too short."""
    if not report.agent_curve or len(report.agent_curve) < 2:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001 — optional dependency
        return None

    if path is None:
        last = report.agent_curve[-1][0]
        path = os.path.join(out_dir, f"backtest_{last}.png")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 1]})

    ax, ay = _curve_xy(report.agent_curve)
    ax1.plot(ax, ay, label="Agent", color="#1f6feb", linewidth=2.2)
    for name, curve in report.benchmark_curves.items():
        bx, by = _curve_xy(curve)
        ax1.plot(bx, by, label=name, linewidth=1.3, alpha=0.85)
    ax1.set_ylabel("Equity ($)")
    ax1.set_title("Walk-Forward: Agent vs Benchmarks")
    ax1.legend(loc="best", fontsize=9)
    ax1.grid(True, alpha=0.25)

    # Cumulative outperformance vs 1/N (the headline benchmark).
    bench = report.benchmark_curves.get("1/N Equal-Weight")
    if bench:
        a0 = report.agent_curve[0][1] or 1.0
        b0 = bench[0][1] or 1.0
        diff = [(report.agent_curve[i][1] / a0) - (bench[i][1] / b0)
                for i in range(min(len(report.agent_curve), len(bench)))]
        dx = ax[:len(diff)]
        ax2.axhline(0, color="#888", linewidth=0.8)
        ax2.fill_between(dx, diff, 0, where=[d >= 0 for d in diff], color="#2da44e", alpha=0.6, interpolate=True)
        ax2.fill_between(dx, diff, 0, where=[d < 0 for d in diff], color="#cf222e", alpha=0.6, interpolate=True)
        ax2.set_ylabel("Agent − 1/N\n(cum. return)")
        ax2.grid(True, alpha=0.25)

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path
