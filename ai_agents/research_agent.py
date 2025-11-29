#%%
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
            "Se l'utente chiede come sta performando un'azienda o un titolo, "
            "usa SEMPRE il tool `get_financials` con il ticker corretto "
            "prima di rispondere. Non fare domande di chiarimento se il ticker è chiaro."
        ),
        HumanMessage(f"Come sta performando {ticker} negli ultimi 12 mesi?")
    ]

    # Step 1: il modello decide i tool
    ai_msg = tool_llm.invoke(messages)
    messages.append(ai_msg)

    # Step 2: esecuzione tool
    for tool_call in ai_msg.tool_calls:
        tool_result = get_financials.invoke(tool_call)
        messages.append(tool_result)

    # Step 3: chiedi un riassunto strutturato
    summary_msg = HumanMessage(
        "In base ai dati finanziari presenti nei messaggi precedenti, "
        "riassumi la performance del titolo in modo strutturato usando lo schema."
    )

    summary = structured_llm.invoke(messages + [summary_msg])

    # summary è un dict compatibile con FinancialSummary
    return FinancialSummary(**summary)