import os
import requests
from dotenv import load_dotenv
from langchain.tools import tool

load_dotenv()

FINDAT_API_KEY = os.getenv("FINDAT_API_KEY")

@tool(description="Get financial matrics for a given ticker symbol")
def get_metrics(ticker: str, period: str = 'ttm', limit: int = 30) -> dict:
    '''
    The snapshot object contains the following fields:
    - ticker (string): the ticker symbol of the company.
    - market_cap (number): The market capitalization of the company.
    - enterprise_value (number): The total value of the company (market cap + debt - cash).
    - price_to_earnings_ratio (number): Price to earnings ratio.
    - price_to_book_ratio (number): Price to book ratio.
    - price_to_sales_ratio (number): Price to sales ratio.
    - enterprise_value_to_ebitda_ratio (number): Enterprise value to EBITDA ratio.
    - enterprise_value_to_revenue_ratio (number): Enterprise value to revenue ratio.
    - free_cash_flow_yield (number): Free cash flow yield.
    - peg_ratio (number): Price to earnings growth ratio.
    - gross_margin (number): Gross profit as a percentage of revenue.
    - operating_margin (number): Operating income as a percentage of revenue.
    - net_margin (number): Net income as a percentage of revenue.
    - return_on_equity (number): Net income as a percentage of shareholders' equity.
    - return_on_assets (number): Net income as a percentage of total assets.
    - return_on_invested_capital (number): Net operating profit after taxes as a percentage of invested capital.
    - asset_turnover (number): Revenue divided by average total assets.
    - inventory_turnover (number): Cost of goods sold divided by average inventory.
    - receivables_turnover (number): Revenue divided by average accounts receivable.
    - days_sales_outstanding (number): Average accounts receivable divided by revenue over the period.
    - operating_cycle (number): Inventory turnover + receivables turnover.
    - working_capital_turnover (number): Revenue divided by average working capital.
    - current_ratio (number): Current assets divided by current liabilities.
    - quick_ratio (number): Quick assets divided by current liabilities.
    - cash_ratio (number): Cash and cash equivalents divided by current liabilities.
    - operating_cash_flow_ratio (number): Operating cash flow divided by current liabilities.
    - debt_to_equity (number): Total debt divided by shareholders' equity.
    - debt_to_assets (number): Total debt divided by total assets.
    - interest_coverage (number): EBIT divided by interest expense.
    - revenue_growth (number): Year-over-year growth in revenue.
    - earnings_growth (number): Year-over-year growth in earnings.
    - book_value_growth (number): Year-over-year growth in book value.
    - earnings_per_share_growth (number): Growth in earnings per share over the period.
    - free_cash_flow_growth (number): Growth in free cash flow over the period.
    - operating_income_growth (number): Growth in operating income over the period.
    - ebitda_growth (number): Growth in EBITDA over the period.
    - payout_ratio (number): Dividends paid as a percentage of net income.
    - earnings_per_share (number): Net income divided by weighted average shares outstanding.
    - book_value_per_share (number): Shareholders' equity divided by shares outstanding.
    - free_cash_flow_per_share (number): Free cash flow divided by shares outstanding.
    '''
    
    # add your API key to the headers
    headers = {
        "X-API-KEY": FINDAT_API_KEY
    }

    # create the URL
    url = (
        f'https://api.financialdatasets.ai/financial-metrics/snapshot'
        f'?ticker={ticker}'
    )

    # make API request
    response = requests.get(url, headers=headers)

    # if status code is 400, 401, 402 or 404 return error message
    if response.status_code != 200:
        return {"error": f"API error {response.status_code} - {response.text}"}

    # parse data from the response
    data = response.json()
    return data.get('snapshot')


