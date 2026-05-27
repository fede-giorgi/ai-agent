"""Warren Buffett-style analyst — deterministic scoring + one LLM synthesis call.

The 8 analysis tools are pure Python scorers (free to run), so the old approach —
an LLM tool-calling loop "deciding" which to call — spent round-trips for no real
saving. Here we run all 8 deterministically, then make a SINGLE judge-tier
(Sonnet) call that weighs the scores + qualitative signals into a
``WarrenBuffettSignal``. The genuine per-stock *judgment* (the synthesis) stays
with the LLM; the mechanical scoring does not.
"""

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from classes.financial_summary import FinancialSummary, WarrenBuffettSignal
from llm import get_judge_llm
from shared_console import console as _console
from tools.analyze_book_value_growth import analyze_book_value_growth
from tools.analyze_consistency import analyze_consistency
from tools.analyze_fundamentals import analyze_fundamentals
from tools.analyze_management_quality import analyze_management_quality
from tools.analyze_moat import analyze_moat
from tools.analyze_pricing_power import analyze_pricing_power
from tools.calculate_intrinsic_value import calculate_intrinsic_value

_SYNTH_PROMPT = """\
You are a Warren Buffett-style investment analyst evaluating {ticker}.
Below are the outputs of eight deterministic analyses (already computed — you do
not call any tools). Weigh them into a single signal.

SIGNAL CALIBRATION:
- BULLISH (70-100): strong moat + consistent earnings + margin_of_safety > 25%.
- BULLISH (40-69): good fundamentals but margin_of_safety modest, or one weak dimension.
- NEUTRAL: mixed — strong moat but fully valued, or improving but short track record.
- BEARISH: deteriorating fundamentals, negative earnings CAGR, trading well above
  intrinsic value, or concerning insider selling with negative news.

Anchor valuation on intrinsic_value.margin_of_safety; use consistency + moat for
durability; use qualitative_signals (insider/news/analyst) only if material.
{debug_note}
Buffett: "It is far better to buy a wonderful company at a fair price than a fair
company at a wonderful price."
"""

_DEBUG_NOTE = (
    "\nNOTE: Debug/testing run. Assign BULLISH >= 55 confidence if the company has "
    "any positive qualities — the goal is to exercise the full trading pipeline."
)


def _qualitative_signals(summary: FinancialSummary) -> dict:
    """News + insider + analyst consensus, summarized (deterministic)."""
    headlines = []
    if summary.recent_news:
        headlines = [ln.strip() for ln in summary.recent_news.split("\n") if ln.strip()][:6]
    net = summary.net_insider_buying or 0
    sentiment = "NET BUYER" if net > 0 else "NET SELLER" if net < 0 else "NEUTRAL"
    return {
        "recent_news_headlines": headlines,
        "insider_activity": {
            "net_buying_usd": net,
            "buy_transactions": summary.insider_buy_count or 0,
            "sell_transactions": summary.insider_sell_count or 0,
            "sentiment": sentiment,
        },
        "analyst_consensus": {
            "period": summary.analyst_estimate_period,
            "revenue_estimate": summary.analyst_revenue_estimate,
            "eps_estimate": summary.analyst_eps_estimate,
        },
    }


def run_analyses(summary: FinancialSummary) -> dict:
    """Run all 8 domain analyses deterministically (no LLM). Returns a dict of results."""
    def _safe(fn):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    return {
        "fundamentals": _safe(lambda: analyze_fundamentals.func(summary=summary)),
        "consistency": _safe(lambda: analyze_consistency.func(summary=summary)),
        "moat": _safe(lambda: analyze_moat.func(summary=summary)),
        "management_quality": _safe(lambda: analyze_management_quality.func(summary=summary)),
        "book_value_growth": _safe(lambda: analyze_book_value_growth.func(summary=summary)),
        "pricing_power": _safe(lambda: analyze_pricing_power.func(summary=summary)),
        "intrinsic_value": _safe(lambda: calculate_intrinsic_value.func(summary=summary)),
        "qualitative_signals": _qualitative_signals(summary),
    }


async def warren_buffett_agent(
    summary: FinancialSummary,
    debug_mode: bool = False,
) -> dict[str, Any]:
    """Score a ticker (deterministic) then synthesize a WarrenBuffettSignal in one LLM call.

    Returns ``{ticker: WarrenBuffettSignal.model_dump()}``.
    """
    _console.print(f"[bold yellow]Analyzing {summary.ticker} (Buffett)...[/bold yellow]")

    analyses = run_analyses(summary)

    llm = get_judge_llm().with_structured_output(WarrenBuffettSignal)
    system = SystemMessage(content=_SYNTH_PROMPT.format(
        ticker=summary.ticker,
        debug_note=_DEBUG_NOTE if debug_mode else "",
    ))
    human = HumanMessage(content=(
        f"Current price: {summary.price}\n"
        f"Deterministic analysis outputs (JSON):\n{json.dumps(analyses, default=str, indent=2)}\n\n"
        "Provide: signal (bullish/bearish/neutral), confidence (0-100, calibrated honestly), "
        "and concise reasoning grounded in these numbers."
    ))

    signal = await llm.ainvoke([system, human])
    _console.print(f"[green]✓ {summary.ticker}: {signal.signal.upper()} {signal.confidence}%[/green]")
    return {summary.ticker: signal.model_dump()}
