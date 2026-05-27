"""WalkForwardHarness — the dev-mode loop.

For each trading session in the window: ask the skip-gate whether to re-run the
full agent pipeline; if so, run it, execute fills, and snapshot state; always
mark-to-market and record. Emits plain per-day log lines (EC2-friendly) and a
final BacktestReport with the agent equity curve, benchmark curves, and metrics.
"""

from __future__ import annotations

from config import MAX_ITERATIONS

from . import benchmarks, config, metrics
from .calendar import TradingCalendar
from .data_cache import PiTDataCache
from .decision_fn import run_one_day
from .execution import ExecutionEngine
from .schema import BacktestReport, DayResult
from .skip_gate import SkipGate, build_snapshot


class WalkForwardHarness:
    def __init__(self, universe: list[str], start: str, end: str,
                 capital: float = config.INITIAL_CAPITAL,
                 risk_profile: int = config.RISK_PROFILE,
                 cache: PiTDataCache | None = None,
                 max_iterations: int = MAX_ITERATIONS,
                 initial_portfolio: dict | None = None,
                 max_sessions: int | None = None,
                 verbose: bool = False,
                 log=print):
        self.universe = sorted(set(universe))
        self.start = start
        self.end = end
        self.capital = capital
        self.risk_profile = risk_profile
        self.cache = cache
        self.max_iterations = max_iterations
        self.initial_portfolio = dict(initial_portfolio or {})
        self.max_sessions = max_sessions   # cap sessions (smoke/debug runs)
        self.verbose = verbose             # render per-day signals + debate + reasoning
        self.log = log

    def run(self) -> BacktestReport:
        cache = self.cache or PiTDataCache(self.universe, self.start, self.end).build(log=self.log)
        cal = TradingCalendar(cache)
        sessions = cal.sessions(self.start, self.end)
        if self.max_sessions:
            sessions = sessions[:self.max_sessions]
        if not sessions:
            raise ValueError(f"No trading sessions in {self.start}..{self.end} — check the cache window.")

        engine = ExecutionEngine(cache, cal)
        gate = SkipGate()
        bench_curves = benchmarks.build_benchmarks(cache, self.universe, sessions, self.capital)

        portfolio, cash, snapshot = dict(self.initial_portfolio), self.capital, None
        agent_curve: list[tuple[str, float]] = []
        day_results: list[DayResult] = []

        self.log(f"Walk-forward: {len(sessions)} sessions {sessions[0]}..{sessions[-1]} | "
                 f"universe={self.universe} | capital=${self.capital:,.0f}")

        try:
            for d in sessions:
                run_today, reason = gate.should_run(d, snapshot, cache, self.universe)
                fills: list[dict] = []
                iters = 0
                if run_today:
                    out = run_one_day(d, self.universe, portfolio, cash, self.risk_profile,
                                      cache, max_iterations=self.max_iterations,
                                      verbose=self.verbose, log=self.log)
                    portfolio, cash, fills = engine.apply(out["final_trades"], portfolio, cash, d)
                    iters = out["iterations"]
                    snapshot = build_snapshot(d, cache, self.universe)
                equity = engine.mark_to_market(portfolio, cash, d)
                agent_curve.append((d, equity))
                day_results.append(DayResult(date=d, ran_pipeline=run_today, reason=reason,
                                             trades=fills, portfolio=dict(portfolio), cash=cash,
                                             equity=equity, iterations=iters))
                tag = "RUN " if run_today else "SKIP"
                cost = ""
                if run_today:
                    try:
                        from llm import format_usage_line
                        cost = f"  | {format_usage_line()}"
                    except Exception:  # noqa: BLE001
                        pass
                self.log(f"[{d}] {tag} ({reason})  equity=${equity:,.2f}  trades={len(fills)}  iters={iters}{cost}")
        except KeyboardInterrupt:
            # Ctrl-C / kill: still produce a report + chart for the days completed so far.
            self.log("\n[interrupted] building a partial report from the completed sessions...")

        # Align benchmark curves to however many sessions the agent actually ran
        # (a no-op on a full run; trims to the completed days on an interrupt).
        n = len(agent_curve)
        bench_partial = {k: v[:n] for k, v in bench_curves.items()}
        return BacktestReport(
            agent_curve=agent_curve,
            benchmark_curves=bench_partial,
            day_results=day_results,
            metrics=metrics.summarize(agent_curve, bench_partial),
        )
