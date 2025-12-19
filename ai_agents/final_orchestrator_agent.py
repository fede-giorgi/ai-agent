import json
from typing import Dict, List, Any
from llm import get_llm

def run_final_orchestrator_agent(
    initial_portfolio: Dict[str, int],
    initial_capital: float,
    warren_signals: Dict[str, Any],
    price_map: Dict[str, float],
    history: List[Dict[str, Any]]
) -> dict:
    """
    Runs the Final Orchestrator Agent to make the definitive trading decision after the iteration loop.
    """
    llm = get_llm()
    
    prompt = f"""
    You are the FinalOrchestratorAgent. You have overseen a simulation loop where a Portfolio Manager, a Monitor, and a What-If Challenger have debated trading strategies for 10 iterations.
    
    Your Goal: Make the FINAL, definitive trading decision to be executed on the user's account.

    Inputs:
    - Initial Portfolio: {json.dumps(initial_portfolio)}
    - Initial Capital: {initial_capital}
    - Warren Buffett Signals: {json.dumps(warren_signals)}
    - Price Map: {json.dumps(price_map)}
    - Iteration History (The debate): {json.dumps(history)}

    Instructions:
    1. Review the history. Look for the most robust, risk-adjusted proposal that passed the Monitor's checks.
    2. Consider the "What-If" critiques. Did they raise valid points?
    3. Decide on the final set of trades. You can choose one of the proposals from the history or synthesize a new one based on the insights.
    4. Ensure the final trades are valid (sufficient capital, no shorting).

    Output JSON ONLY:
    {{
      "agent": "final_orchestrator",
      "final_decision_reasoning": "Explanation of why this strategy was chosen over others",
      "final_trades": [{{"action":"buy|sell","ticker":"XXX","shares":int}}],
      "expected_portfolio": {{"TICKER": int}},
      "expected_capital": float
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
            "agent": "final_orchestrator",
            "final_decision_reasoning": "Error parsing LLM response",
            "final_trades": []
        }