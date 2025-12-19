import json
from pydantic import BaseModel, Field
from typing import List

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage

from llm import get_llm
from models.financial_summary import FinancialSummary, ToolStatus, Error, Result, ResearchAgentOutput
from tools.get_financials import get_financials
from tools.get_metrics import get_metrics
from tools.get_financial_line_items import get_financial_line_items
from tools.get_stock_prices import get_stock_prices

REQUIRED_LIST = [
    "capital_expenditure",
    "depreciation_and_amortization",
    "net_income",
    "outstanding_shares",
    "total_assets",
    "total_liabilities",
    "shareholders_equity",
    "dividends_and_other_cash_distributions",
    "issuance_or_purchase_of_equity_shares",
    "gross_profit",
    "revenue",
    "free_cash_flow",
    "current_assets",
    "current_liabilities",
]

system_instruction = SystemMessage(content=
    """You are ResearchAgent. Your goal is to process the raw JSON data from financial tools (`get_financials`, `get_metrics`, `get_financial_line_items`, `get_stock_prices`) for a given stock ticker and structure it into a specific JSON format defined by the `Result` model.

        Rules:
        - You will be given the raw JSON output from each of the three tools.
        - Populate the `financial_summary` field using the provided data. All fields in `FinancialSummary` must be present; use null if a value is not available.
        - Specifically for the `price` field in `FinancialSummary`, extract the latest closing price from the `get_stock_prices` output.
        - Any keys from the raw tool output that are not part of the `FinancialSummary` model should be placed in the `extra_fields` dictionary.
        - If a tool failed (indicated by an error message instead of JSON), reflect this in the `tool_status` and `errors` fields.
        - Analyze the provided data for any potential inconsistencies or quality issues and add notes to `data_quality_notes`. For example, if `revenue` from one tool is drastically different from another.
        - Use numbers when the source data is a number. If it's a string that looks like a number, try to convert it. If unsure, keep the original value and add a note to `data_quality_notes`. Do not use `NaN` or `Infinity`; use `null` instead.
        - Output a valid JSON object matching the `Result` model only. Do not add any extra prose or markdown.
    """
)

user_content = HumanMessage(content=
    """Please process the following data for the ticker: {ticker}

    Raw output from `get_financials`:
    {financials_data}

    Raw output from `get_metrics`:
    {metrics_data}

    Raw output from `get_financial_line_items`:
    {line_items_data}

    Raw output from `get_stock_prices`:
    {prices_data}
    """
)


prompt_template = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are ResearchAgent. Your goal is to process the raw JSON data from financial tools (`get_financials`, `get_metrics`, `get_financial_line_items`, `get_stock_prices`) for a given stock ticker and structure it into a specific JSON format defined by the `Result` model.

            Rules:
            - You will be given the raw JSON output from each of the three tools.
            - Populate the `financial_summary` field using the provided data. All fields in `FinancialSummary` must be present; use null if a value is not available.
            - Specifically for the `price` field in `FinancialSummary`, extract the latest closing price from the `get_stock_prices` output.
            - Any keys from the raw tool output that are not part of the `FinancialSummary` model should be placed in the `extra_fields` dictionary.
            - If a tool failed (indicated by an error message instead of JSON), reflect this in the `tool_status` and `errors` fields.
            - Analyze the provided data for any potential inconsistencies or quality issues and add notes to `data_quality_notes`. For example, if `revenue` from one tool is drastically different from another.
            - Use numbers when the source data is a number. If it's a string that looks like a number, try to convert it. If unsure, keep the original value and add a note to `data_quality_notes`. Do not use `NaN` or `Infinity`; use `null` instead.
            - Output a valid JSON object matching the `Result` model only. Do not add any extra prose or markdown.
            """,
        ),
        (
            "human",
            """Please process the following data for the ticker: {ticker}

            Raw output from `get_financials`:
            {financials_data}

            Raw output from `get_metrics`:
            {metrics_data}

            Raw output from `get_financial_line_items`:
            {line_items_data}

            Raw output from `get_stock_prices`:
            {prices_data}
            """,
                    ),
                ]
            )


def run_research_agent(
        tickers: List[str],
        backtesting_date: str = None
        ) -> str:
    """
    Runs the research agent to gather and structure financial data for a list of tickers.
    """
    llm = get_llm()
    structured_llm = llm.with_structured_output(Result)
    processing_chain = prompt_template | structured_llm

    agent_output = ResearchAgentOutput(requested_tickers=tickers)

    for ticker in tickers:
        print(f"Researching {ticker}...")
        financials_data_str: str
        metrics_data_str: str
        line_items_data_str: str
        prices_data_str: str
        
        financials_data, metrics_data, line_items_data, prices_data = {}, {}, {}, {}
        errors = []
        tool_status = {"get_financials": "ok", "get_metrics": "ok", "get_financial_line_items": "ok", "get_stock_prices": "ok"}

        try:
            financials_data = get_financials.func(
                ticker=ticker, period="annual", 
                limit=10, 
                end_date=backtesting_date
                )
            financials_data_str = json.dumps(financials_data)
        except Exception as e:
            financials_data_str = f"Error: {e}"
            errors.append(Error(tool="get_financials", message=str(e), ticker=ticker))
            tool_status["get_financials"] = "error"

        try:
            metrics_data = get_metrics.func(
                ticker=ticker, 
                period="annual", 
                limit=10, 
                end_date=backtesting_date)
            metrics_data_str = json.dumps(metrics_data)
        except Exception as e:
            metrics_data_str = f"Error: {e}"
            errors.append(Error(tool="get_metrics", message=str(e), ticker=ticker))
            tool_status["get_metrics"] = "error"
        
        try:
            line_items_data = get_financial_line_items.func(
                tickers=[ticker], 
                line_items=REQUIRED_LIST, 
                period="annual", 
                limit=10, 
                end_date=backtesting_date
            )
            line_items_data_str = json.dumps(line_items_data)
        except Exception as e:
            line_items_data_str = f"Error: {e}"
            errors.append(Error(tool="get_financial_line_items", message=str(e), ticker=ticker))
            tool_status["get_financial_line_items"] = "error"

        try:
            prices_data = get_stock_prices.func(
                ticker=ticker,
                end_date=backtesting_date
                )
            prices_data_str = json.dumps(prices_data)
        except Exception as e:
            prices_data_str = f"Error: {e}"
            errors.append(Error(tool="get_stock_prices", message=str(e), ticker=ticker))
            tool_status["get_stock_prices"] = "error"
        
        if all(status == "error" for status in tool_status.values()):
            agent_output.errors.extend(errors)
            continue

        try:
            result = processing_chain.invoke({
                "ticker": ticker,
                "financials_data": financials_data_str,
                "metrics_data": metrics_data_str,
                "line_items_data": line_items_data_str,
                "prices_data": prices_data_str,
            })
            result.tool_status = ToolStatus(**tool_status)
            result.errors.extend(errors)
            agent_output.results.append(result)
            print(f"Research result for {ticker}: {result.model_dump_json(indent=2)}")
            
        except Exception as e:
            agent_output.errors.append(Error(tool="processing_chain", message=str(e), ticker=ticker))


    return agent_output.model_dump_json(indent=2)