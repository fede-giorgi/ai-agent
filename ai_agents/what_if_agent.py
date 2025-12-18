import json
from typing import Dict, List, Any, Union
from llm import get_llm

def run_what_if_agent(
    current_portfolio: Dict[str, int],
    available_capital: float,
    proposed_trades: List[Dict[str, Union[str, int, float]]],
    price_map: Dict[str, float],
    warren_signals: Dict[str, Any] = None
) -> dict:
    """
    Runs the What-If Agent to simulate the portfolio after applying trades.
    """
    llm = get_llm()
    
    prompt = f"""
    You are WhatIfAgent. Input: current_portfolio (ticker->shares), available_capital, proposed_trades, price_map, and (optional) warren_signals. Your job: simulate the portfolio after applying the proposed trades and report how it would look.
    
    Inputs:
    - Current Portfolio: {json.dumps(current_portfolio)}
    - Available Capital: {available_capital}
    - Proposed Trades: {json.dumps(proposed_trades)}
    - Price Map: {json.dumps(price_map)}
    - Warren Signals: {json.dumps(warren_signals) if warren_signals else "None"}

    Simulation rules:
    - Apply all sells first, then buys.
    - No shorting: selling more than held becomes a violation; cap at held and record a note (but do not go negative).
    - Cash update:
        cash_after = available_capital + sell_proceeds - buy_cost
    - Portfolio shares update:
        buy adds shares; sell subtracts shares; remove tickers with 0 shares.
    - Compute value snapshots using price_map:
        position_value = shares * price
        total_value = cash_after + Σ(position_value)
        weights = position_value / total_value (cash has its own weight)

    Output JSON ONLY:
    {{
      "agent":"what_if",
      "before":{{
        "portfolio": {{...}},
        "cash": number,
        "total_value": number,
        "weights":{{"TICKER": number, "CASH": number}}
      }},
      "after":{{
        "portfolio": {{...}},
        "cash": number,
        "total_value": number,
        "weights":{{"TICKER": number, "CASH": number}}
      }},
      "applied_trades":[{{"action":"...","ticker":"...","shares":...,"price":number,"value":number}}],
      "notes":[...],
      "violations":[...]
    }}
    """
    
    response = llm.invoke(prompt)
    try:
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        return json.loads(content)
    except json.JSONDecodeError:
        return {
            "agent": "what_if",
            "before": {},
            "after": {},
            "applied_trades": [],
            "notes": ["Error parsing LLM response"],
            "violations": [str(response.content)]
        }
