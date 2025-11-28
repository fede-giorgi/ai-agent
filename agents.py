#%%
import getpass, os, requests
from dotenv import load_dotenv

from langchain.tools import tool
from langchain.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from pydantic import BaseModel
from typing import Literal, List

from llm import get_llm

load_dotenv()

FINDAT_API_KEY = os.getenv("FINDAT_API_KEY")

# %%
@tool(description="Get financial data for a given ticker symbol")
def get_financials(ticker: str, period: str = 'ttm', limit: int = 30) -> dict:
    
    # add your API key to the headers
    headers = {
        "X-API-KEY": FINDAT_API_KEY
    }

    # create the URL
    url = (
        f'https://api.financialdatasets.ai/financials/'
        f'?ticker={ticker}'
        f'&period={period}'
        f'&limit={limit}'
    )

    # make API request
    response = requests.get(url, headers=headers)

    # if status code is 400, 401, 402 or 404 return error message
    if response.status_code != 200:
        return {"error": f"API error {response.status_code} - {response.text}"}

    # parse data from the response
    data = response.json()
    return data.get('financials', {})

class KeyMetric(BaseModel):
    name: str
    value: float | None
    unit: str | None

class FinancialSummary(BaseModel):
    ticker: str
    period: str
    trend_12m: Literal["up", "down", "flat", "unknown"]
    key_metrics: List[KeyMetric]
    narrative: str

tool_llm = get_llm().bind_tools([get_financials])

base_llm = get_llm()
structured_llm = base_llm.with_structured_output(
    schema=FinancialSummary.model_json_schema(),
    method="json_mode"
)

# # %%
# # Step 1: primo giro, il modello decide se chiamare il tool
# messages = [
#     SystemMessage(
#         "Se l'utente chiede come sta performando un'azienda o un titolo, "
#         "usa SEMPRE il tool `get_financials` con il ticker corretto "
#         "prima di rispondere. Non fare domande di chiarimento se il ticker è chiaro."
#     ),
#     HumanMessage("Come sta performando TSLA negli ultimi 12 mesi?")
# ]


# ai_msg = model.invoke(messages)
# messages.append(ai_msg)

# print("Tool calls:", ai_msg.tool_calls)

# # Step 2: esegui i tool (se ce ne sono)
# for tool_call in ai_msg.tool_calls:
#     tool_result = get_financials.invoke(tool_call)
#     messages.append(tool_result)

# # Step 3: risposta finale basata sui dati reali
# final_response = model.invoke(messages)
# print("RISPOSTA FINALE:\n", final_response.content)
# %%

def run_financial_agent(ticker: str, period: str = "ttm") -> FinancialSummary:
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

# %%
import json
from langchain.messages import SystemMessage, HumanMessage

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

# %%


# %%
