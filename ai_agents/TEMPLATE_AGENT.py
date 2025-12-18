import json
from langchain.messages import SystemMessage, HumanMessage

from llm import get_llm
from models.financial_summary import FinancialSummary

analysis_llm = get_llm()

def run_analysis_agent(summary: FinancialSummary, user_question: str) -> str:
    json_summary = summary.model_dump()

    messages = [
        SystemMessage(
            "You are a financial analyst. You will receive a JSON object named 'financial_summary' containing ticker, period, trend_12m, key_metrics, and narrative. Use only the provided data to answer the user's question. Do not invent or hallucinate additional numbers or information. Provide a clear, concise, and professional analysis based strictly on the summary."
        ),
        HumanMessage(
            content=(
                "Here is the structured summary of the stock:\n\n"
                f"{json.dumps(json_summary, indent=2)}\n\n"
                f"User question: {user_question}"
            )
        )
    ]

    resp = analysis_llm.invoke(messages)
    return resp.content