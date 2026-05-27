"""Research Agent — deterministic, parallel per-ticker data assembly (no LLM).

Replaces the old LLM tool-calling + structured-compilation loop (which pushed the
full financial JSON through the model 2-3x per ticker for zero judgment) with a
plain Python assembler. Data still comes from FinancialDatasets.ai; in backtest
mode the same calls are served — masked to the cutoff — from the point-in-time
cache. Same signature and ``ResearchAgentOutput`` return, so callers are unchanged.
"""

import asyncio

from classes.financial_summary import Error, ResearchAgentOutput
from ai_agents.research_data import assemble_result
from shared_console import console as _console


async def run_research_agent(
    tickers: list[str],
    backtesting_date: str | None = None,
) -> ResearchAgentOutput:
    """Assemble a Result per ticker, in parallel, with no LLM calls.

    Args:
        tickers: Ticker symbols to research.
        backtesting_date: Optional YYYY-MM-DD cutoff; threaded to every endpoint
                          as ``end_date`` (and enforced by the cache when backtesting).

    Returns:
        ResearchAgentOutput with a Result per ticker (Errors collected separately).
    """
    out = ResearchAgentOutput(requested_tickers=tickers)

    async def _one(ticker: str):
        _console.print(f"[bold cyan]Researching {ticker} (deterministic)...[/bold cyan]")
        # assemble_result is sync (network/cache I/O) — run off the event loop.
        return await asyncio.to_thread(assemble_result, ticker, backtesting_date)

    outcomes = await asyncio.gather(*[_one(t) for t in tickers], return_exceptions=True)
    for ticker, outcome in zip(tickers, outcomes):
        if isinstance(outcome, Exception):
            out.errors.append(Error(tool="research", message=str(outcome), ticker=ticker))
        else:
            out.results.append(outcome)
            _console.print(f"  [green]✓ {ticker} assembled.[/green]")
    return out
