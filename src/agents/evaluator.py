from pydantic import BaseModel, Field
from src.utils.llm import call_llm
from src.graph.state import AgentState

class EvaluationOutput(BaseModel):
    score: float = Field(description="Confidence score from 0 to 1")
    recommendation: str = Field(description="PROCEED, REPLAN, or ABORT")
    reasoning: str

def evaluator_agent(state: AgentState):
    prediction = state.get("prediction_output", {})
    
    signals = state["data"].get("analyst_signals", {})
    
    prompt = f"""
    You are the Risk Evaluator. 
    Simulation to evaluate: {prediction}
    Based on signals: {signals}

    Task:
    1. Verify logical consistency between simulation and signals.
    2. Grade utility from 0 to 1.
    3. If there's a major conflict, set recommendation to 'REPLAN'.
    """
    
    result = call_llm(prompt, EvaluationOutput, "evaluator", state)
    
    return {"evaluator_output": result.model_dump()}