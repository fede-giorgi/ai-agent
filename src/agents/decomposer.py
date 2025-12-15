from pydantic import BaseModel, Field
from typing import List, Optional
from src.utils.llm import call_llm
from src.graph.state import AgentState
from src.utils.analysts import ANALYST_CONFIG
class DecompositionOutput(BaseModel):
    priority_analysts: List[str] = Field(description="Analyst keys to activate.")
    plan: str = Field(description="Step-by-step strategic plan.")
    reasoning: str

def task_decomposer(state: AgentState):
    tickers = state["data"]["tickers"]
    previous_eval = state.get("evaluator_output", {})
    feedback_loop = ""
    available_keys = list(ANALYST_CONFIG.keys())
    
    if previous_eval and previous_eval.get("recommendation") == "REPLAN":
        feedback_loop = f"""
        ATTENTION: Your previous plan was REJECTED.
        Reason: {previous_eval.get('reasoning')}
        Please adjust your strategy and select different analysts.
        """

    prompt = f"""
    You are the Task Decomposer
    Your objective is to create an investment strategy for: {tickers}.
    
    {feedback_loop}

    AVAILABLE ANALYST KEYS (You must use these exact keys):
    {", ".join(available_keys)}

    TASK:
    1. Select the most relevant analysts for the current market condition.
    2. Provide a step-by-step strategic plan for the team.
    3. Explain your reasoning for selecting these specific experts.
    """
    
  
    decomposition = call_llm(prompt, DecompositionOutput, "decomposer", state)
    
    return {
        "decomposer_output": decomposition.model_dump()
    }