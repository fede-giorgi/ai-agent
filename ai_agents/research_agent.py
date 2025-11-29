from langchain.messages import SystemMessage, HumanMessage

from llm import get_llm
from tools.get_financials import get_financials
from models.financial_summary import FinancialSummary

import getpass, os, requests
from dotenv import load_dotenv

llm = get_llm()
tool_llm = llm.bind_tools([get_financials])
structured_llm = llm.with_structured_output(
    schema=FinancialSummary.model_json_schema(),
    method="json_mode",
)


def run_research_agent(ticker: str, period: str = "ttm") -> FinancialSummary:
    messages = [
        SystemMessage(
            "If the user asks about how a company or stock has been performing, ALWAYS use the `get_financials` tool with the correct ticker before answering. Do not ask clarifying questions if the ticker is clearly provided. Respond only after retrieving financial data."
        ),
        HumanMessage(
            f"How has {ticker} performed over the past 12 months?"
            )
    ]

    ai_msg = tool_llm.invoke(messages)
    messages.append(ai_msg)

    for tool_call in ai_msg.tool_calls:
        tool_result = get_financials.invoke(tool_call)
        messages.append(tool_result)

    summary_msg = HumanMessage(
        "Based on the financial data contained in the previous messages, summarize the stock’s performance using the provided schema, following the exact JSON structure."
    )

    summary = structured_llm.invoke(messages + [summary_msg])

    return FinancialSummary(**summary)