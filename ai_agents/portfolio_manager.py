from typing import Dict, List, Union
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

def run_portfolio_manager_agent(
    current_portfolio: Dict[str, Union[int, float]],
    warren_buffett_signals: Dict[str, dict],
    risk_profile: int,
    available_capital: float,
    financial_data: Dict[str, FinancialSummary],
) -> List[Dict[str, Union[str, int, float]]]:
    """
    Generates a list of proposed trades based on agent signals and risk profile.

    Args:
        current_portfolio: The current state of the portfolio.
        warren_buffett_signals: The signals from the Warren Buffett agent.
        risk_profile: The user's risk tolerance (1-10).
        available_capital: The cash available to invest.
        financial_data: A dictionary of FinancialSummary objects, keyed by ticker.

    Returns:
        A list of proposed trades.
    """
    proposed_trades = []
    
    # Risk factor: higher risk profile means more aggressive trades
    risk_factor = risk_profile / 10.0

    # 1. Handle bearish signals (sell)
    for ticker, holdings in current_portfolio.items():
        if ticker in warren_buffett_signals:
            signal_data = warren_buffett_signals[ticker]
            if signal_data.get("signal") == "bearish":
                # Sell a portion based on confidence and risk profile
                sell_fraction = (signal_data.get("confidence", 50) / 100.0) * (1.2 - risk_factor) # Sell more if less risky profile
                shares_to_sell = int(holdings * sell_fraction)
                if shares_to_sell > 0:
                    proposed_trades.append({"action": "sell", "ticker": ticker, "shares": shares_to_sell})

    # 2. Handle bullish signals (buy)
    
    # Find bullish stocks not in portfolio
    bullish_stocks_to_consider = []
    for ticker, signal_data in warren_buffett_signals.items():
        if signal_data.get("signal") == "bullish":
            bullish_stocks_to_consider.append(ticker)
            # If already in portfolio, consider buying more
            if ticker in current_portfolio:
                price = get_price_from_summary(financial_data[ticker])
                if price > 0 and available_capital > price:
                     # Invest a portion of capital based on confidence and risk
                    investment_amount = available_capital * (signal_data.get("confidence", 50) / 100.0) * risk_factor * 0.1 # invest 10% of capital per stock
                    shares_to_buy = int(investment_amount / price)
                    if shares_to_buy > 0:
                        proposed_trades.append({"action": "buy", "ticker": ticker, "shares": shares_to_buy})
                        available_capital -= shares_to_buy * price


    # Allocate remaining capital to new bullish stocks
    if bullish_stocks_to_consider and available_capital > 0:
        capital_per_stock = available_capital / len(bullish_stocks_to_consider)
        for ticker in bullish_stocks_to_consider:
            if ticker not in current_portfolio: # only new stocks
                price = get_price_from_summary(financial_data[ticker])
                if price > 0:
                    shares_to_buy = int(capital_per_stock / price)
                    if shares_to_buy > 0:
                        proposed_trades.append({"action": "buy", "ticker": ticker, "shares": shares_to_buy})

    return proposed_trades
