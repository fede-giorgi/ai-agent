import os
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta

from langchain.tools import tool

load_dotenv()

FINDAT_API_KEY = os.getenv("FINDAT_API_KEY")

@tool(description="Get historical stock prices for a given ticker symbol")
def get_stock_prices(ticker: str, start_date: str = None, end_date: str = None, interval: str = 'day', interval_multiplier: int = 1):
    """
    Retrieves historical stock prices for a given ticker.
    
    Args:
        ticker (str): The ticker symbol (e.g., "AAPL").
        start_date (str): Start date in YYYY-MM-DD format.
        end_date (str): End date in YYYY-MM-DD format.
        interval (str, optional): Time interval ('minute', 'day', 'week', 'month', 'year'). Defaults to 'day'.
        interval_multiplier (int, optional): Multiplier for the interval. Defaults to 1.
        
    Returns:
        dict: A dictionary containing the stock prices.
    """


    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
    if not start_date:
        # Default to 7 days lookback to ensure we catch a trading day
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    # create the URL
    url = (
        f'https://api.financialdatasets.ai/prices/'
        f'?ticker={ticker}'
        f'&interval={interval}'
        f'&interval_multiplier={interval_multiplier}'
        f'&start_date={start_date}'
        f'&end_date={end_date}'
    )
    
    if not FINDAT_API_KEY:
        raise ValueError(
            "API key for Financial Datasets not found. Please set the FINDAT_API_KEY environment variable."
        )

    # add your API key to the headers
    headers = {
        "X-API-KEY": FINDAT_API_KEY
        }

    # make API request
    response = requests.get(url, headers=headers)

    # if status code is 400, 401, 402 or 404 return error message
    if response.status_code != 200:
        return {"error": f"API error {response.status_code} - {response.text}"}

    # parse data from the response
    ans = response.json()
    return ans