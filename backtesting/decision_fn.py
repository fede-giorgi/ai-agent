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
    from async_utils import bounded_gather
    from config import MAX_ANALYST_CONCURRENCY
    tasks = [warren_buffett_agent(s, debug_mode=False) for s in financial_data.values()]
    results = await bounded_gather(*tasks, limit=MAX_ANALYST_CONCURRENCY,
                                   return_exceptions=True)
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
                max_iterations: int = MAX_ITERATIONS, verbose: bool = False, log=print) -> dict:
    """Run Research → Buffett → debate → Orchestrator for one cutoff; return target
    trades, the as-of price map, signals, and the number of debate rounds used.

    When ``verbose`` is set, render the full per-day narrative (signals table, the
    PM/Monitor/What-If debate, and the Orchestrator's reasoning) so a backtest can
    be inspected for hallucination / stuck-on-a-wrong-path behaviour."""
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

    if verbose:
        _render_day(cutoff, signals, history, final)

    return {
        "final_trades": final.get("final_trades", []),
        "price_map": price_map,
        "signals": signals,
        "iterations": len(history),
    }


def _trades_str(trades: list[dict] | None) -> str:
    if not trades:
        return "no trades"
    return ", ".join(f"{str(t.get('action','')).upper()} {t.get('shares')} {t.get('ticker')}"
                     for t in trades if isinstance(t, dict))


def _render_day(cutoff: str, signals: dict, history: list[dict], final: dict) -> None:
    """Print the full per-day agent narrative (signals + debate + decision)."""
    from rich import box
    from rich.panel import Panel
    from rich.table import Table

    from shared_console import console

    console.rule(f"[bold cyan]{cutoff} — agent reasoning[/bold cyan]")

    # Signals table (the per-stock Buffett conviction + why).
    st = Table(title="Warren Buffett signals", box=box.ROUNDED, show_lines=False)
    st.add_column("Ticker", style="cyan")
    st.add_column("Signal")
    st.add_column("Conf", justify="right")
    st.add_column("Reasoning", overflow="fold")
    for tk, s in (signals or {}).items():
        sig = str(s.get("signal", "")).upper()
        color = {"BULLISH": "green", "BEARISH": "red"}.get(sig, "yellow")
        st.add_row(tk, f"[{color}]{sig}[/{color}]", str(s.get("confidence", "")),
                   (s.get("reasoning", "") or "")[:240])
    console.print(st)

    # The PM → Monitor → What-If debate, round by round.
    for h in history:
        i = h.get("iteration")
        pm = (h.get("pm_proposal") or {}).get("proposed_trades", [])
        mon = h.get("monitor_check") or {}
        wi = h.get("what_if_critique") or {}
        valid = "[green]valid[/green]" if mon.get("is_valid") else "[red]violations[/red]"
        console.print(f"[bold]Iter {i}[/bold]  PM: {_trades_str(pm)}  |  Monitor: {valid}")
        crit = wi.get("critique")
        if crit:
            console.print(f"   [magenta]What-If:[/magenta] {str(crit)[:240]}")

    # The Final Orchestrator's decision + reasoning.
    reasoning = final.get("final_decision_reasoning") or final.get("reasoning") or "(none)"
    console.print(Panel(str(reasoning), title="Final decision", border_style="green", padding=(0, 1)))
    console.print(f"[bold]Final trades:[/bold] {_trades_str(final.get('final_trades', []))}")
