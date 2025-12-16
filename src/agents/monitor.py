import json
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from src.utils.llm import call_llm
from src.graph.state import AgentState

class MonitorOutput(BaseModel):
    is_valid: bool = Field(description="Whether the proposal is logically consistent.")
    reasoning: str = Field(description="Brief explanation.")
    suggested_correction: str = Field(description="How to fix the proposal if invalid.")

def monitor_agent(state: AgentState, analyst_id: str, proposal: dict):
    template = ChatPromptTemplate.from_messages([
        ("system", "You are the Conflict Monitoring unit (ACC). Verify if the analyst proposal for {ticker} makes sense logically and matches their known investment style. Reject hallucinations."),
        ("human", "Analyst: {analyst_id}\nProposal: {proposal}")
    ])
    prompt = template.invoke({
        "analyst_id": analyst_id,
        "ticker": state["data"]["tickers"],
        "proposal": json.dumps(proposal)
    })
    return call_llm(prompt, MonitorOutput, "monitor", state)