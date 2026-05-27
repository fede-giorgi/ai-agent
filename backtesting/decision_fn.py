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
    → What-If debate, and the Orchestrator's decision — laid out so it reads
    end-to-end and the reasoning can be judged: each iteration's outcome is a
    skimmable one-line header, the prose is dimmed below it, and a What-If round
    that just repeats the previous one collapses to a single line. Nothing is
    truncated. ``console`` defaults to the shared Rich console; tests pass a
    recording one.
    """
    from rich import box
    from rich.markup import escape
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
            console.print(Panel(escape(why), title=f"{escape(tk)} — Buffett reasoning",
                                title_align="left", border_style="cyan", padding=(0, 1)))

    # The PM → Monitor → What-If debate, round by round.
    console.rule("[bold]Debate — Portfolio Manager → Monitor → What-If[/bold]", style="dim")
    prev = None
    for h in history:
        _render_iteration(console, h, prev)
        prev = h

    # The Final Orchestrator's decision + full reasoning.
    reasoning = final.get("final_decision_reasoning") or final.get("reasoning") or "(none)"
    console.print(Panel(escape(str(reasoning)), title="Final decision", border_style="green",
                        title_align="left", padding=(0, 1)))
    final_trades = _trades_str(final.get("final_trades", []))
    console.print(f"[bold green]▸ {escape(cutoff)} decision:[/bold green] "
                  f"[bold]{escape(final_trades)}[/bold]  "
                  f"[dim]({len(history)} debate iteration{'s' if len(history) != 1 else ''})[/dim]")


def _wi_signature(wi: dict) -> tuple:
    """Identity of a What-If challenge (critique + alternative) — used to detect a
    round that merely repeats the previous one so it can be collapsed."""
    alt = wi.get("alternative_scenario") or {}
    alt_trades = alt.get("proposed_trades", []) if isinstance(alt, dict) else []
    return ((wi.get("critique") or "").strip(),
            tuple((t.get("action"), t.get("ticker"), t.get("shares"))
                  for t in alt_trades if isinstance(t, dict)))


def _render_iteration(console, h: dict, prev_h: dict | None = None) -> None:
    """Render one debate round: a one-line outcome header (PM action · Monitor
    verdict · What-If stance) plus the agents' full reasoning, dimmed. A What-If
    that repeats the prior round collapses to a single line."""
    from rich.markup import escape
    from rich.panel import Panel
    from rich.table import Table

    i = h.get("iteration")
    pm = h.get("pm_proposal") or {}
    mon = h.get("monitor_check") or {}
    wi = h.get("what_if_critique") or {}

    pm_action = _trades_str(pm.get("proposed_trades") or [])
    mon_ok = bool(mon.get("is_valid"))
    crit = (wi.get("critique") or "").strip()
    alt = wi.get("alternative_scenario") or {}
    alt_trades = alt.get("proposed_trades", []) if isinstance(alt, dict) else []
    unchanged = bool(prev_h) and crit and _wi_signature(wi) == _wi_signature(
        prev_h.get("what_if_critique") or {})

    if not crit:
        wi_head = "endorses (no challenge)"
    elif alt_trades:
        wi_head = f"proposes {_trades_str(alt_trades)}"
    else:
        wi_head = "challenges, suggests holding"

    # Skimmable one-line outcome in the panel header.
    title = (f"Iteration {i}   PM [bold]{escape(pm_action)}[/bold]   "
             f"Monitor {'[green]valid[/green]' if mon_ok else '[red]BLOCKED[/red]'}   "
             f"What-If [magenta]{escape(wi_head)}[/magenta]"
             + ("  [dim](unchanged)[/dim]" if unchanged else ""))

    grid = Table.grid(padding=(0, 2))
    grid.add_column(justify="right", style="bold", no_wrap=True)
    grid.add_column(overflow="fold")

    # PM rationale (dimmed prose).
    pm_cell = "\n".join(f"[dim]• {escape(n)}[/dim]" for n in (pm.get("notes") or [])) or "[dim]—[/dim]"
    grid.add_row("[green]Portfolio Mgr[/green]", pm_cell)

    # Monitor: only elaborate when it blocked something.
    if mon_ok:
        mon_cell = "[dim]all constraints satisfied[/dim]"
    else:
        mon_cell = "\n".join(
            f"[red]✗ {escape(str(v.get('type')))}[/red] "
            f"[dim]{escape(str(v.get('ticker')))}: {escape(str(v.get('detail')))}[/dim]"
            for v in (mon.get("violations") or [])) or "[red]✗ blocked[/red]"
    grid.add_row("[blue]Monitor[/blue]", mon_cell)

    # What-If: collapse a repeat round; else full critique + alternative + why.
    if not crit:
        wi_cell = "[dim]no challenge raised[/dim]"
    elif unchanged:
        wi_cell = ("[dim]same challenge as the previous round — a standing "
                   "disagreement left for the Orchestrator to settle[/dim]")
    else:
        parts = [f"[dim]{escape(crit)}[/dim]"]
        if isinstance(alt, dict) and alt.get("description"):
            parts.append(f"[magenta]alternative:[/magenta] [dim]{escape(alt['description'])}[/dim]")
        why = (wi.get("reasoning") or "").strip()
        if why and why != crit:
            parts.append(f"[dim italic]why: {escape(why)}[/dim italic]")
        wi_cell = "\n".join(parts)
    grid.add_row("[magenta]What-If[/magenta]", wi_cell)

    console.print(Panel(grid, title=title, title_align="left", border_style="dim", padding=(0, 1)))
