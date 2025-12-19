import os
import requests
from dotenv import load_dotenv

from langchain.tools import tool

load_dotenv()

API_KEY = os.getenv("FINDAT_API_KEY")

@tool(description="Get financial line items for a given ticker symbol")
def get_financial_line_items(tickers, line_items=None, period="ttm", limit=30):
    """
    Retrieves specific financial line items for a list of tickers, including:
    * `capital_expenditure`
    * `depreciation_and_amortization`
    * `net_income`
    * `outstanding_shares` (available as `weighted_average_shares`)
    * `total_assets`
    * `total_liabilities`
    * `shareholders_equity`
    * `dividends_and_other_cash_distributions`
    * `issuance_or_purchase_of_equity_shares`
    * `gross_profit`
    * `revenue` (available as `total_revenue`)
    * `free_cash_flow`
    * `current_assets`
    * `current_liabilities`

    Args:
        tickers (list): A list of stock tickers (e.g., ["AAPL", "NVDA"]).
        line_items (list, optional): A list of financial line items to retrieve.
        period (str, optional): The reporting period. Can be "annual", "quarterly", or "ttm". Defaults to "annual".
        limit (int, optional): The number of periods to retrieve. Defaults to 10.

    Returns:
        dict: A dictionary containing the financial line items for the specified tickers.
    """
    

    url = "https://api.financialdatasets.ai/financials/search/line-items"

    if not API_KEY:
        raise ValueError(
            "API key for Financial Datasets not found. Please set the FINANCIAL_DATASETS_API_KEY environment variable."
        )

    # add your API key to the headers
    headers = {
        "X-API-KEY": API_KEY, 
        "Content-Type": "application/json"
        }

    payload = {
        "tickers": tickers,
        "line_items": line_items,
        "period": period,
        "limit": limit,
    }

    # make API request
    response = requests.post(url, headers=headers, json=payload)

    # if status code is 400, 401, 402 or 404 return error message
    if response.status_code != 200:
        return {"error": f"API error {response.status_code} - {response.text}"}

    # parse data from the response
    ans = response.json()
    return ans