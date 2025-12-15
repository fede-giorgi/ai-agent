from pydantic import BaseModel, Field
from src.utils.llm import call_llm
from src.graph.state import AgentState

class EvaluationOutput(BaseModel):
    score: float = Field(description="Confidence score from 0 to 1")
    recommendation: str = Field(description="PROCEED, REPLAN, or ABORT")
    reasoning: str

def evaluator_agent(state: AgentState):
    prediction = state.get("prediction_output", {})
    signals = state.get("analyst_signals", {})
    
    prompt = f"""
    You are the Risk Evaluator (OFC). 
    The following market prediction has been generated: {prediction}
    Based on these analyst signals: {signals}

    Your task:
    1. Is the prediction consistent with the signals?
    2. Is the risk/reward ratio acceptable (>0.7)?
    3. If you detect a severe logical contradiction, respond with 'REPLAN'.
    """
    
    result = call_llm(prompt, EvaluationOutput, "evaluator", state)
    return {"evaluator_output": result}
