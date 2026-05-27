"""Final Orchestrator Agent — makes the definitive trading decision after the multi-iteration debate loop."""

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from rich import box
from rich.console import Console
from rich.table import Table

from llm import get_judge_llm


def _text(content) -> str:
    """Return plain text from an LLM response (handles str or list of content blocks)."""
    if isinstance(content, list):
        return " ".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return content if isinstance(content, str) else str(content)


def _trade(t: dict) -> dict:
    return {"action": t.get("action"), "ticker": t.get("ticker"), "shares": t.get("shares")}


def compact_history(history: list[dict]) -> list[dict]:
    """Strip the debate down to decision-relevant fields (trades, validity, the
    What-If critique) — keeps the cross-iteration consensus view the orchestrator
    needs while removing the verbose PM notes/reasoning blobs that bloated the
    prompt to millions of tokens on non-converging days."""
    out = []
    for h in history:
        pm = (h.get("pm_proposal") or {}).get("proposed_trades", []) or []
        mon = h.get("monitor_check") or {}
        wi = h.get("what_if_critique") or {}
        alt = wi.get("alternative_scenario") or {}
        alt_trades = alt.get("proposed_trades", []) if isinstance(alt, dict) else []
        out.append({
            "iteration": h.get("iteration"),
            "pm_trades": [_trade(t) for t in pm if isinstance(t, dict)],
            "monitor_valid": bool(mon.get("is_valid", False)),
            "what_if_critique": (wi.get("critique") or "")[:300],
            "what_if_alt_trades": [_trade(t) for t in alt_trades if isinstance(t, dict)],
        })
    return out


def _last_valid_trades(history: list[dict]) -> list[dict]:
    """The most recent Monitor-approved PM proposal — a safe fallback if parsing fails."""
    for h in reversed(history):
        if (h.get("monitor_check") or {}).get("is_valid"):
            return (h.get("pm_proposal") or {}).get("proposed_trades", []) or []
    return []


def _extract_json(s: str) -> str:
    """Pull the JSON object out of an LLM reply (handles ```json fences and prose)."""
    s = s.strip()
    if s.startswith("```"):
        s = s[3:]
        if s[:4].lower() == "json":
            s = s[4:]
        s = s.split("```", 1)[0]
    start, end = s.find("{"), s.rfind("}")
    return s[start:end + 1] if (start != -1 and end > start) else s


def run_final_orchestrator_agent(
    initial_portfolio: dict[str, int],
    initial_capital: float,
    warren_signals: dict[str, Any],
    price_map: dict[str, float],
    history: list[dict],
) -> dict:
    """
    Makes the definitive trading decision after reviewing the full multi-iteration debate.

    Synthesises or selects from the Portfolio Manager, Monitor, and What-If proposals
    across all iterations, applying consensus checks, Monitor compliance, and
    Warren Buffett signal alignment.

    Args:
        initial_portfolio: Holdings at the start of this run (ticker → shares).
        initial_capital: Cash available at the start of this run.
        warren_signals: Dict of ticker → WarrenBuffettSignal dict.
        price_map: Dict of ticker → current price.
        history: Full iteration history list (PM proposal, monitor result, what-if critique per iteration).

    Returns:
        dict with ``agent``, ``final_decision_reasoning``, ``final_trades``,
        ``expected_portfolio``, and ``expected_capital``.
    """
    llm = get_judge_llm()
    
    system_message = SystemMessage(
        content="""You are FinalOrchestratorAgent — the Chief Investment Officer of a Warren Buffett-style hedge fund.
You have just received a compressed summary of the full multi-iteration debate between the Portfolio Manager, Monitor, and What-If Agent.

YOUR GOAL: Make the single FINAL, definitive trading decision that will be executed on the user's account.

DECISION FRAMEWORK:
1. CONSENSUS CHECK: Which trade proposals appeared consistently across multiple iterations (stable conviction)?
   Prefer stable proposals over one-off suggestions that changed every iteration.
2. MONITOR COMPLIANCE: Only consider proposals that passed (or would pass) Monitor validation.
   If all iterations had violations, synthesise a conservative valid plan.
3. WHAT-IF SYNTHESIS: Did the What-If Agent raise a point that was never addressed?
   If yes, incorporate it. If the PM consistently refuted it, side with the PM.
4. CAPITAL EFFICIENCY: Ensure the final trades deploy capital productively (avoid leaving >20% uninvested
   unless risk profile is Low 1-3).
5. ORIGINAL SIGNALS: Always cross-reference with Warren Buffett signals. BEARISH → do not buy. BULLISH + high confidence → reward with allocation.

SYNTHESIS vs. SELECTION:
- PREFER selecting the best single iteration's trades if one clearly dominated.
- SYNTHESISE a new plan only if no single iteration was satisfactory.

HARD CONSTRAINTS (same as Monitor):
- No shorting: sell_shares ≤ current holdings.
- Budget: Σ(buy × price) − Σ(sell × price) ≤ available_capital.
- Only trade tickers with a valid price in price_map.

Output JSON ONLY:
{
  "agent": "final_orchestrator",
  "final_decision_reasoning": "Which iteration/proposal was chosen and why, addressing PM vs What-If debate",
  "final_trades": [{"action": "buy|sell", "ticker": "XXX", "shares": int}],
  "expected_portfolio": {"TICKER": int},
  "expected_capital": float
}
"""
    )

    human_message = HumanMessage(
        content=f"""
        Inputs:
        - Initial Portfolio: {json.dumps(initial_portfolio)}
        - Initial Capital: {initial_capital}
        - Warren Buffett Signals: {json.dumps(warren_signals)}
        - Price Map: {json.dumps(price_map)}
        - Iteration History (compacted debate): {json.dumps(compact_history(history))}
        """
    )

    response = llm.invoke([system_message, human_message])
    try:
        parsed = json.loads(_extract_json(_text(response.content)))
        if not isinstance(parsed, dict):
            raise ValueError("orchestrator response was not a JSON object")
        parsed.setdefault("agent", "final_orchestrator")
        parsed.setdefault("final_trades", [])
        return parsed
    except (json.JSONDecodeError, ValueError):
        # Don't silently produce "no trades" — fall back to the debate's last
        # Monitor-approved proposal so a parse glitch never nukes the day.
        fallback = _last_valid_trades(history)
        return {
            "agent": "final_orchestrator",
            "final_decision_reasoning": ("Orchestrator response could not be parsed; "
                                         "defaulted to the last Monitor-valid PM proposal."),
            "final_trades": fallback,
        }

def generate_ascii_chart(history: list[dict]) -> Table:
    """
    Generates a Rich Table showing trade proposals (quantities) over iterations for both agents.
    """
    table = Table(title="Trade Proposals Over Iterations (PM vs What-If)", box=box.ROUNDED)
    table.add_column("Iter", justify="center", style="cyan")
    table.add_column("Ticker", style="magenta")
    table.add_column("PM Proposal", justify="right", style="green")
    table.add_column("What-If Proposal", justify="right", style="blue")
    
    for iteration in history:
        iter_num = iteration.get("iteration", "?")

        pm_trades = {}
        if "pm_proposal" in iteration and "proposed_trades" in iteration["pm_proposal"]:
            for trade in iteration["pm_proposal"]["proposed_trades"]:
                qty = trade["shares"] if trade["action"] == "buy" else -trade["shares"]
                pm_trades[trade["ticker"]] = qty

        wi_trades = {}
        if "what_if_critique" in iteration and "alternative_scenario" in iteration["what_if_critique"]:
            alt = iteration["what_if_critique"]["alternative_scenario"]
            if alt and "proposed_trades" in alt:
                for trade in alt["proposed_trades"]:
                    qty = trade["shares"] if trade["action"] == "buy" else -trade["shares"]
                    wi_trades[trade["ticker"]] = qty

        all_tickers = set(pm_trades.keys()) | set(wi_trades.keys())

        if not all_tickers:
            table.add_row(str(iter_num), "-", "-", "-")
            continue

        for i, ticker in enumerate(sorted(all_tickers)):
            pm_qty = f"{pm_trades.get(ticker, 0):+d}" if ticker in pm_trades else "-"
            wi_qty = f"{wi_trades.get(ticker, 0):+d}" if ticker in wi_trades else "-"
            row_iter = str(iter_num) if i == 0 else ""  # show iter number only on first ticker row
            table.add_row(row_iter, ticker, pm_qty, wi_qty)
        
        table.add_section()

    return table