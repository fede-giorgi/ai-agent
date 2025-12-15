from pydantic import BaseModel, Field
from src.utils.llm import call_llm
from src.graph.state import AgentState

class PredictionOutput(BaseModel):
    predicted_trend: str = Field(description="Probable direction of the stock: BULLISH, BEARISH, or NEUTRAL")
    confidence: int = Field(description="Confidence score from 0 to 100", ge=0, le=100)
    reasoning: str = Field(description="Detailed simulation of the next 5-10 days based on analyst input.")

def predictor_agent(state: AgentState):
    """
    Mental Simulation (OFC): Projects the future state of the market 
    by synthesizing all analyst signals.
    """
    
    analyst_signals = state["data"].get("analyst_signals", {})
    tickers = state["data"]["tickers"]
    
    prompt = f"""
    You are the Predictor (Orbitofrontal Cortex). Your role is Mental Simulation.
    
    Current Tickers: {tickers}
    Analyst Signals: {analyst_signals}
    
    Task:
    1. Synthesize the conflicting or matching signals from the analysts.
    2. Simulate the most likely market outcome for the next 5-10 trading days.
    3. Determine the expected trend and your confidence level in this simulation.
    """
    
  
    prediction = call_llm(prompt, PredictionOutput, "predictor", state)

    return {
        "prediction_output": prediction.model_dump(),
        "messages": state["messages"] 
    }