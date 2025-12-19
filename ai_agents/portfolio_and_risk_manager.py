import json
from typing import Dict, List, Any
from llm import get_llm

def run_portfolio_manager_agent(
    current_portfolio: Dict[str, int],
    available_capital: float,
    risk_profile: int,
    warren_signals: Dict[str, Any],
    price_map: Dict[str, float],
    previous_feedback: Dict[str, Any] = None
) -> dict:
    """
    Runs the Portfolio Manager Agent to propose trades based on signals and risk profile.
    """
    llm = get_llm()
    
    prompt = f"""
    You are PortfolioManagerAgent. Your goal is to optimize a stock portfolio based on Warren Buffett-style analysis signals, risk profile, and capital constraints. You must make smart, calculated decisions to maximize long-term value while managing risk. You are part of an iterative refinement process.

    Inputs:
    - Current Portfolio: {json.dumps(current_portfolio)}
    - Available Capital: {available_capital}
    - Risk Profile: {risk_profile}
    - Warren Signals: {json.dumps(warren_signals)}
    - Price Map: {json.dumps(price_map)}
    - Feedback from Previous Iteration: {json.dumps(previous_feedback) if previous_feedback else "None (First Iteration)"}

    Strategy & Logic:
    1. **Signal Interpretation**:
       - **Bullish**: Strong buy signal. High confidence (80%+) implies high conviction.
       - **Bearish**: Strong sell signal. Reduce exposure immediately.
       - **Neutral**: Hold or trim. Do not add to neutral positions unless they are significantly underweight and fundamentals are still decent.

    2. **Risk Management (Risk Profile {risk_profile}/10)**:
       - **Low Risk (1-3)**: EXTREME CAUTION. Prioritize capital preservation above all. If Risk Profile is 1, DO NOT BUY any stocks; only sell to raise cash if needed. Keep a large cash buffer.
       - **Mid Risk (4-7)**: Balanced approach. Cash buffer 5-15%. Scale position sizes based on conviction (Confidence score).
       - **High Risk (8-10)**: Aggressive growth. Low cash buffer (<5%). Concentrate capital in top highest-confidence Bullish ideas.

    3. **Position Sizing**:
       - Calculate a "Target Allocation" for each stock based on: Signal Strength + Confidence + Risk Profile.
       - Example: A Bullish stock with 90% confidence in a High Risk portfolio might target 20-30% allocation.
       - A Neutral stock might target 5-10% or 0% depending on better opportunities.
       - A Bearish stock should target 0%.

    4. **Execution Rules**:
       - **Sell First**: Generate cash from Bearish/Neutral sells before buying.
       - **Buy Second**: Allocate available cash to Bullish stocks with highest conviction.
       - **Rebalance**: If a position exceeds its target weight significantly, trim it.

    Refinement Logic:
    - If the "What-If" agent suggested a better alternative in the feedback, consider adopting it.

    Hard Constraints:
    - Trades must be JSON objects: {{"action":"buy|sell","ticker":"XXX","shares":int>0}}
    - No shorting: do not sell more shares than currently held.
    - Only trade tickers with a valid positive price in price_map.
    - Avoid micro trades: skip if trade_value < 100 (shares*price).
    - Try to keep net buy cost within available_capital + expected sell proceeds (assume sells execute first).


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
