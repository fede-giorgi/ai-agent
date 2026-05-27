"""Per-day decision function: run the existing agent pipeline for one cutoff date.

Headless (plain logging, no Rich spinners — friendly to EC2 / piped logs) and
served entirely from the point-in-time cache via ``install_cache`` so it makes
zero API calls and can never see the future. Reuses the real agents; the debate
loop mirrors ``main.py`` but stops early via ``convergence.has_converged``.
"""

from __future__ import annotations

import asyncio

from config import MAX_ITERATIONS
from convergence import convergence_reason, has_converged

from .as_of_provider import AsOfProvider
from .data_cache import PiTDataCache
from .tool_injection import install_cache


async def _warren_all(financial_data: dict) -> dict:
    from ai_agents.warren_buffet_agent import warren_buffett_agent
    tasks = [warren_buffett_agent(s, debug_mode=False) for s in financial_data.values()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    signals: dict = {}
    for ticker, res in zip(financial_data.keys(), results):
        if isinstance(res, Exception):
            continue
        if res and ticker in res:
            signals.update(res)
    return signals


def _debate_loop(portfolio, cash, risk_profile, signals, price_map,
                 max_iterations, log) -> list[dict]:
    from ai_agents.portfolio_and_risk_manager import run_portfolio_manager_agent
    from ai_agents.monitor import run_monitor_agent
    from ai_agents.what_if_agent import run_what_if_agent

    history: list[dict] = []
    for i in range(1, max_iterations + 1):
        pm = run_portfolio_manager_agent(
            portfolio, cash, risk_profile, signals, price_map, i, max_iterations,
            history, force_trades=False,  # realistic: never force trades in a backtest
        )
        proposed = pm.get("proposed_trades", [])
        monitor = run_monitor_agent(proposed, portfolio, cash, price_map, i, max_iterations, history)
        what_if = {}
        if i < max_iterations:
            what_if = run_what_if_agent(portfolio, cash, proposed, price_map, i,
                                        max_iterations, signals, history)
        history.append({"iteration": i, "pm_proposal": pm,
                        "monitor_check": monitor, "what_if_critique": what_if})
        if has_converged(history):
            log(f"    {convergence_reason(history)}")
            break
    return history


def run_one_day(cutoff: str, universe: list[str], portfolio: dict, cash: float,
                risk_profile: int, cache: PiTDataCache, *,
                max_iterations: int = MAX_ITERATIONS, log=print) -> dict:
    """Run Research → Buffett → debate → Orchestrator for one cutoff; return target
    trades, the as-of price map, signals, and the number of debate rounds used."""
    from ai_agents.research_agent import run_research_agent
    from ai_agents.final_orchestrator_agent import run_final_orchestrator_agent

    provider = AsOfProvider(cache, cutoff)
    with install_cache(provider):
        research = asyncio.run(run_research_agent(universe, backtesting_date=cutoff))
        financial_data = {r.financial_summary.ticker: r.financial_summary
                          for r in research.results}
        signals = asyncio.run(_warren_all(financial_data))
        price_map = {t: (d.price or 0.0) for t, d in financial_data.items()}
        history = _debate_loop(portfolio, cash, risk_profile, signals, price_map,
                               max_iterations, log)
        final = run_final_orchestrator_agent(portfolio, cash, signals, price_map, history)

    return {
        "final_trades": final.get("final_trades", []),
        "price_map": price_map,
        "signals": signals,
        "iterations": len(history),
    }
