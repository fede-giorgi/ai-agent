from typing import Dict, List, Union, Tuple
from models.financial_summary import FinancialSummary

def get_price_from_summary(summary: FinancialSummary) -> float:
    """
    Estimates the price of a stock from the FinancialSummary.
    Uses market_cap / outstanding_shares as a proxy.
    Returns 0.0 if data is not available.
    """
    if summary.market_cap and summary.outstanding_shares and summary.outstanding_shares > 0:
        return summary.market_cap / summary.outstanding_shares
    return 0.0

def run_monitor_agent(
    proposed_trades: List[Dict[str, Union[str, int, float]]],
    available_capital: float,
    financial_data: Dict[str, FinancialSummary],
) -> Tuple[bool, str]:
    """
    Checks if the proposed trades are within the available capital.

    Args:
        proposed_trades: A list of trades to be executed.
        available_capital: The amount of cash available for trading.
        financial_data: A dictionary of FinancialSummary objects, keyed by ticker.

    Returns:
        A tuple containing:
        - bool: True if the trades are valid, False otherwise.
        - str: A message explaining the result.
    """
    total_cost = 0.0

    for trade in proposed_trades:
        action = trade.get("action")
        ticker = trade.get("ticker")
        shares = trade.get("shares")

        if not all([action, ticker, shares]):
            continue

        if ticker not in financial_data:
            return False, f"Invalid trade: No financial data for {ticker}."

        price = get_price_from_summary(financial_data[ticker])
        if price == 0.0:
            return False, f"Invalid trade: Cannot determine price for {ticker}."
        
        trade_value = price * shares

        if action == "buy":
            total_cost += trade_value
        elif action == "sell":
            total_cost -= trade_value

    if total_cost > available_capital:
        return False, f"Trade is too expensive. Cost: ${total_cost:,.2f}, Capital: ${available_capital:,.2f}"

    return True, "Trades are within budget."
