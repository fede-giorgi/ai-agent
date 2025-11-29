import json
from langchain.messages import SystemMessage, HumanMessage

from llm import get_llm
from models.financial_summary import FinancialSummary

analysis_llm = get_llm()

def run_analysis_agent(summary: FinancialSummary, user_question: str) -> str:
    json_summary = summary.model_dump()

    messages = [
        SystemMessage(
            "Sei un analista finanziario. "
            "Riceverai un oggetto JSON 'financial_summary' con la struttura:\n"
            "ticker, period, trend_12m, key_metrics, narrative.\n"
            "Rispondi in modo chiaro usando questi dati, senza inventare numeri aggiuntivi."
        ),
        HumanMessage(
            content=(
                "Ecco il riassunto strutturato del titolo:\n\n"
                f"{json.dumps(json_summary, indent=2)}\n\n"
                f"Domanda dell'utente: {user_question}"
            )
        )
    ]

    resp = analysis_llm.invoke(messages)
    return resp.content