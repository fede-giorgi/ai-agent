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


def _render_day(cutoff: str, signals: dict, history: list[dict], final: dict,
                console=None) -> None:
    """Print the full per-day agent narrative — signals, the complete PM → Monitor
    → What-If debate (every agent's full text, no truncation), and the Orchestrator's
    decision — so a run can be read end-to-end and judged for sound reasoning.

    ``console`` defaults to the shared Rich console; tests pass a recording one.
    """
    from rich import box
    from rich.panel import Panel
    from rich.table import Table

    if console is None:
        from shared_console import console

    console.rule(f"[bold cyan]{cutoff} — agent reasoning[/bold cyan]")

    # Buffett signals: a compact verdict table, then each ticker's FULL reasoning
    # (a cramped table column truncated it; a panel folds it readably).
    st = Table(title="Warren Buffett signals", box=box.ROUNDED, show_lines=False)
    st.add_column("Ticker", style="cyan")
    st.add_column("Signal")
    st.add_column("Conf", justify="right")
    for tk, s in (signals or {}).items():
        sig = str(s.get("signal", "")).upper()
        color = {"BULLISH": "green", "BEARISH": "red"}.get(sig, "yellow")
        st.add_row(tk, f"[{color}]{sig}[/{color}]", str(s.get("confidence", "")))
    console.print(st)
    for tk, s in (signals or {}).items():
        why = (s.get("reasoning") or "").strip()
        if why:
            console.print(Panel(why, title=f"{tk} — Buffett reasoning", title_align="left",
                                border_style="cyan", padding=(0, 1)))

    # The PM → Monitor → What-If debate, round by round — full text, no truncation.
    console.rule("[bold]Debate — Portfolio Manager → Monitor → What-If[/bold]", style="dim")
    for h in history:
        _render_iteration(console, h)

    # The Final Orchestrator's decision + full reasoning.
    reasoning = final.get("final_decision_reasoning") or final.get("reasoning") or "(none)"
    console.print(Panel(str(reasoning), title="Final decision", border_style="green",
                        title_align="left", padding=(0, 1)))
    console.print(f"[bold]Final trades:[/bold] {_trades_str(final.get('final_trades', []))}")


def _render_iteration(console, h: dict) -> None:
    """Render one debate round as a labelled panel: what the PM proposed and why,
    what the Monitor found (with concrete violations), and the What-If challenge
    (full critique + the alternative it puts forward). Nothing truncated."""
    from rich.panel import Panel
    from rich.table import Table

    i = h.get("iteration")
    pm = h.get("pm_proposal") or {}
    mon = h.get("monitor_check") or {}
    wi = h.get("what_if_critique") or {}

    # Portfolio Manager: trades + per-trade rationale notes.
    pm_lines = [f"[bold]proposes:[/bold] {_trades_str(pm.get('proposed_trades') or [])}"]
    pm_lines += [f"  • {n}" for n in (pm.get("notes") or [])]

    # Monitor: validity + the concrete constraint violations / cash summary.
    if mon.get("is_valid"):
        mon_lines = ["[green]VALID[/green] — no constraint violations"]
    else:
        mon_lines = ["[red]VIOLATIONS[/red]"]
        mon_lines += [f"  ✗ [red]{v.get('type')}[/red] {v.get('ticker')}: {v.get('detail')}"
                      for v in (mon.get("violations") or [])]
    mon_lines += [f"  • {n}" for n in (mon.get("notes") or [])]

    # What-If: full critique + the concrete alternative + its reasoning.
    wi_lines: list[str] = []
    crit = (wi.get("critique") or "").strip()
    if crit:
        wi_lines.append(crit)
        alt = wi.get("alternative_scenario") or {}
        if isinstance(alt, dict):
            if alt.get("description"):
                wi_lines.append(f"[magenta]alternative:[/magenta] {alt['description']}")
            if alt.get("proposed_trades"):
                wi_lines.append(f"[magenta]proposes:[/magenta] {_trades_str(alt['proposed_trades'])}")
        why = (wi.get("reasoning") or "").strip()
        if why and why != crit:
            wi_lines.append(f"[dim]why:[/dim] {why}")
    else:
        wi_lines.append("[dim](no challenge — PM proposal accepted, or final iteration)[/dim]")

    grid = Table.grid(padding=(0, 2))
    grid.add_column(justify="right", style="bold", no_wrap=True)
    grid.add_column(overflow="fold")
    grid.add_row("[green]Portfolio Mgr[/green]", "\n".join(pm_lines))
    grid.add_row("[blue]Monitor[/blue]", "\n".join(mon_lines))
    grid.add_row("[magenta]What-If[/magenta]", "\n".join(wi_lines))
    console.print(Panel(grid, title=f"Iteration {i}", title_align="left",
                        border_style="dim", padding=(0, 1)))
