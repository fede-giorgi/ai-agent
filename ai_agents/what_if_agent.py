import json
from typing import Dict, List, Union

def run_what_if_agent(
    current_portfolio: Dict[str, Union[int, float]],
    proposed_trades: List[Dict[str, Union[str, int, float]]],
) -> str:
    """
    Simulates the impact of proposed trades on the current portfolio.

    Args:
        current_portfolio: A dictionary representing the current portfolio,
                           e.g., {"AAPL": 10, "GOOGL": 5}.
        proposed_trades: A list of dictionaries, where each dictionary
                         represents a trade, e.g.,
                         [{"action": "buy", "ticker": "MSFT", "shares": 2},
                          {"action": "sell", "ticker": "AAPL", "shares": 3}].

    Returns:
        A JSON string representing the new portfolio after the trades.
    """
    new_portfolio = current_portfolio.copy()

    for trade in proposed_trades:
        action = trade.get("action")
        ticker = trade.get("ticker")
        shares = trade.get("shares")

        if not all([action, ticker, shares]):
            # Skip invalid trade entry
            continue

        if action == "buy":
            new_portfolio[ticker] = new_portfolio.get(ticker, 0) + shares
        elif action == "sell":
            current_shares = new_portfolio.get(ticker, 0)
            new_portfolio[ticker] = max(0, current_shares - shares)
            if new_portfolio[ticker] == 0:
                del new_portfolio[ticker]

    return json.dumps(new_portfolio, indent=4)
