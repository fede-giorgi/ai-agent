import os
import requests
from dotenv import load_dotenv
from langchain.tools import tool

load_dotenv()

FINDAT_API_KEY = os.getenv("FINDAT_API_KEY")

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