import os
import requests
from dotenv import load_dotenv
from langchain.tools import tool

load_dotenv()

FINDAT_API_KEY = os.getenv("FINDAT_API_KEY")

@tool(description="Get financial line items for a given ticker symbol")
def get_financial_line_items(tickers: list[str], 
                             line_items: list[str], 
                             period: str = "annual", 
                             limit: int = 30,
                             end_date: str = None
                             ) -> dict:
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

    # check if API key is set
    if not FINDAT_API_KEY:
        raise ValueError(
            "API key for Financial Datasets not found. Please set the FINDAT_API_KEY environment variable."
        )

    # add your API key to the headers
    headers = {
        "X-API-KEY": FINDAT_API_KEY, 
        "Content-Type": "application/json"
        }

    # prepare the payload
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
    data = response.json()
    search_results = data.get("search_results")

    if end_date and search_results:
        # Keep only past reports (relative to the end_date)
        filtered = [
            f for f in search_results
            if f.get('report_period') and f.get('report_period') <= end_date
        ]

        if filtered:
            return {"search_results": filtered}
        else:
            return {"error": f"No data found before {end_date}"}

    # return all search results if no end_date is specified
    return data