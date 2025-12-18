import json
from typing import Dict, List, Any
from llm import get_llm

def run_portfolio_manager_agent(
    current_portfolio: Dict[str, int],
    available_capital: float,
    risk_profile: int,
    warren_signals: Dict[str, Any],
    price_map: Dict[str, float]
) -> dict:
    """
    Runs the Portfolio Manager Agent to propose trades based on signals and risk profile.
    """
    llm = get_llm()
    
    prompt = f"""
    You are PortfolioManagerAgent. Input: current_portfolio (ticker->shares), available_capital (cash), risk_profile (1-10), warren_signals JSON, and price_map (ticker->estimated_price). Your job: propose a practical set of trades (buy/sell shares) that reflects the Warren agent signals and the user’s risk_profile.

    Inputs:
    - Current Portfolio: {json.dumps(current_portfolio)}
    - Available Capital: {available_capital}
    - Risk Profile: {risk_profile}
    - Warren Signals: {json.dumps(warren_signals)}
    - Price Map: {json.dumps(price_map)}

    Interpret signals:
    - signal ∈ {{bullish, bearish, neutral}}
    - CI (confidence) is 0–100; treat it as position conviction.
    - Prefer higher CI bullish for buys; higher CI bearish for sells.

    Risk behavior:
    - Low risk (1–3): small changes, diversification, reduce bearish exposure strongly, avoid concentration.
    - Mid (4–7): moderate changes, scale position sizes with CI.
    - High (8–10): more aggressive reallocation, allow concentration into top bullish/high-CI names.

    Hard constraints:
    - Trades must be JSON objects: {{"action":"buy|sell","ticker":"XXX","shares":int>0}}
    - No shorting: do not sell more shares than currently held.
    - Only trade tickers with a valid positive price in price_map.
    - Avoid micro trades: skip if trade_value < 100 (shares*price).
    - Try to keep net buy cost within available_capital + expected sell proceeds (assume sells execute first).

    Heuristic sizing (simple and deterministic):
    - Sell sizing for bearish tickers: sell_fraction = (CI/100) * (1.2 - risk_profile/10); clamp 0..1
    - Buy sizing for bullish tickers: allocate buy_budget proportional to (CI/100) * (risk_profile/10)
    - Prefer adding to existing bullish positions before opening new ones unless high risk_profile.

    Output JSON ONLY:
    {{
      "agent":"portfolio_manager",
      "proposed_trades":[{{"action":"...","ticker":"...","shares":...}}],
      "target_allocation":{{"TICKER": weight_0_to_1, "...": ...}},
      "notes":[...],
      "errors":[...]
    }}
    """
    
    response = llm.invoke(prompt)
    try:
        # Clean up potential markdown code blocks
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        return json.loads(content)
    except json.JSONDecodeError:
        return {
            "agent": "portfolio_manager",
            "proposed_trades": [],
            "target_allocation": {},
            "notes": ["Error parsing LLM response"],
            "errors": [str(response.content)]
        }
