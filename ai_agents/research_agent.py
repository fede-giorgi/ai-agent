from typing import List
from tools.get_financials import get_financials
from tools.get_metrics import get_metrics
from tools.get_financial_line_items import get_financial_line_items
from models.financial_summary import FinancialSummary

def run_research_agent(tickers: List[str]) -> List[FinancialSummary]:
    """
    Runs the research agent to gather financial data for a list of tickers.
    """
    financial_summaries = []
    for ticker in tickers:
        print(f"Researching {ticker}...")
        try:
            # 1. Get financials
            financials_data = get_financials.func(
                ticker=ticker, period="ttm"
            )

            # 2. Get metrics
            metrics_data = get_metrics.func(ticker=ticker)

            # 3. Get line items
            line_items_data = get_financial_line_items.func(
                tickers=[ticker],
                line_items=[
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
                    "current_liabilities"
                ],
                period="ttm"
            )

            # 4. Combine data and create FinancialSummary
            summary_data = {
                "ticker": ticker,
                **financials_data,
                **metrics_data,
                **line_items_data,
            }
            
            # Filter out keys that are not in the FinancialSummary model
            valid_keys = FinancialSummary.model_fields.keys()
            filtered_data = {k: v for k, v in summary_data.items() if k in valid_keys}

            financial_summaries.append(FinancialSummary(**filtered_data))
        except Exception as e:
            print(f"Could not retrieve data for {ticker}: {e}")

    return financial_summaries
