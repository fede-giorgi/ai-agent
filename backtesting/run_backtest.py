"""CLI entry for the walk-forward (no-refit) backtest — dev mode / EC2.

    python -m backtesting.run_backtest --start 2026-01-01 --end 2026-03-31 \
        --tickers AAPL,MSFT,NVDA --capital 100000 --risk 6

``main.py --dev`` also routes here. Per-day progress is plain log lines (clean in
piped/EC2 logs); the final report uses Rich tables (auto-plain when not a TTY).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta

from rich import box
from rich.console import Console
from rich.table import Table

from config import DEFAULT_TICKERS, MAX_ITERATIONS

from . import config
from .data_cache import PiTDataCache
from .schema import BacktestReport
from .walk_forward import WalkForwardHarness

console = Console()


def _render(report: BacktestReport) -> None:
    m = report.metrics
    a = m["agent"]

    summary = Table(title="Walk-Forward Result — Agent", box=box.ROUNDED, show_header=False)
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", justify="right")
    summary.add_row("Total return", f"{a['total_return']:+.2%}")
    summary.add_row("Annualized", f"{a['annualized_return']:+.2%}")
    summary.add_row("Sharpe", f"{a['sharpe']:.2f}")
    summary.add_row("Max drawdown", f"{a['max_drawdown']:.2%}")
    summary.add_row("Final equity", f"${a['final_equity']:,.2f}")
    console.print(summary)

    cmp = Table(title="Benchmark Comparison", box=box.ROUNDED)
    cmp.add_column("Benchmark", style="magenta")
    cmp.add_column("Return", justify="right")
    cmp.add_column("Alpha vs agent", justify="right")
    cmp.add_column("Daily win rate", justify="right")
    for name, b in m["benchmarks"].items():
        cmp.add_row(name, f"{b['total_return']:+.2%}",
                    f"{b['alpha']:+.2%}", f"{b['daily_win_rate']:.0%}")
    console.print(cmp)

    verdict = f"Agent beat {m['n_beaten']}/{m['n_benchmarks']} benchmarks"
    style = "bold green" if m["n_beaten"] == m["n_benchmarks"] else (
        "yellow" if m["n_beaten"] else "bold red")
    console.print(f"[{style}]{verdict}[/{style}]  (beaten: {', '.join(m['beaten']) or 'none'})")

    ran = sum(1 for d in report.day_results if d.ran_pipeline)
    console.print(f"[dim]{ran}/{len(report.day_results)} sessions ran the full pipeline "
                  f"(skip-gate saved {len(report.day_results) - ran}).[/dim]")
    try:
        from llm import format_usage_line
        console.print(f"[dim]tokens/cost: {format_usage_line()}[/dim]")
    except Exception:  # noqa: BLE001
        pass


def main(argv: list[str] | None = None) -> BacktestReport:
    p = argparse.ArgumentParser(prog="backtesting.run_backtest",
                                description="Walk-forward (no-refit) backtest")
    p.add_argument("--start", help="YYYY-MM-DD (default: ~95 days before end)")
    p.add_argument("--end", help="YYYY-MM-DD (default: today)")
    p.add_argument("--tickers", help="comma-separated; default = config.DEFAULT_TICKERS")
    p.add_argument("--capital", type=float, default=config.INITIAL_CAPITAL)
    p.add_argument("--risk", type=int, default=config.RISK_PROFILE)
    p.add_argument("--max-iters", type=int, default=MAX_ITERATIONS)
    p.add_argument("--screen-top", type=int, default=None,
                   help="screen the universe to the top-K candidates (as-of window start) before analysis")
    p.add_argument("--debug", action="store_true",
                   help="smoke test: first ticker only, first 2 sessions — verify it runs before a full backtest")
    p.add_argument("--verbose", action="store_true",
                   help="render each RUN day's signals table, PM/Monitor/What-If debate, and Orchestrator reasoning")
    p.add_argument("--no-plot", dest="plot", action="store_false", help="skip the equity-curve PNG")
    p.set_defaults(plot=True)
    p.add_argument("--rebuild-cache", action="store_true")
    # Ignore run-mode flags passed through from main.py (--dev/--demo).
    args, _unknown = p.parse_known_args(argv)

    end = args.end or datetime.today().strftime("%Y-%m-%d")
    start = args.start or (datetime.strptime(end, "%Y-%m-%d") - timedelta(days=95)).strftime("%Y-%m-%d")
    universe = ([t.strip().upper() for t in args.tickers.split(",") if t.strip()]
                if args.tickers else list(DEFAULT_TICKERS))

    max_sessions = None
    if args.debug:
        universe = universe[:1]
        max_sessions = 2
        console.print("[bold yellow]DEBUG SMOKE TEST[/bold yellow] [dim]— 1 ticker, 2 sessions "
                      "(verifies the pipeline before a full backtest)[/dim]")

    console.rule("[bold green]Agentic AI Hedge Fund — Walk-Forward Backtest[/bold green]")
    cache = PiTDataCache(universe, start, end).build(force=args.rebuild_cache, log=console.print)

    # Optional: screen a large universe down to the top-K candidates (as-of the
    # window start, fixed for the whole run — no survivorship bias or look-ahead).
    if args.screen_top:
        from .screening import screen_universe
        full_n = len(universe)
        universe = screen_universe(cache, universe, start, top_k=args.screen_top)
        console.print(f"[dim]Screened {full_n} → {len(universe)}: {', '.join(universe)}[/dim]")

    harness = WalkForwardHarness(universe, start, end, capital=args.capital,
                                 risk_profile=args.risk, cache=cache,
                                 max_iterations=args.max_iters, max_sessions=max_sessions,
                                 verbose=(args.verbose or args.debug),  # smoke is verbose by default
                                 log=console.print)
    report = harness.run()
    _render(report)

    # Terminal sparkline + PNG of equity / outperformance.
    from .plots import ascii_sparkline, save_report_chart
    spark = ascii_sparkline([e for _, e in report.agent_curve])
    if spark:
        console.print(f"[dim]agent equity:[/dim] {spark}")
    if args.plot:
        path = save_report_chart(report)
        if path:
            console.print(f"[green]Chart saved → {path}[/green]")
        else:
            console.print("[dim](chart skipped — matplotlib unavailable or curve too short)[/dim]")
    return report


if __name__ == "__main__":
    main()
