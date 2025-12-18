import json
from rich.console import Console
from rich.table import Table
from datetime import datetime, timedelta

from ai_agents.research_agent import run_research_agent
from ai_agents.warren_buffet_agent import warren_buffett_agent
from ai_agents.portfolio_manager import run_portfolio_manager_agent
from ai_agents.what_if_agent import run_what_if_agent
from ai_agents.monitor import run_monitor_agent
from ai_agents.tickers import TICKERS
from models.financial_summary import FinancialSummary
from tools.get_stock_price import get_stock_prices

console = Console()

def get_portfolio():
    """
    Prompts the user to either provide their existing portfolio or use a default one.
    """
    has_portfolio = console.input("Do you have an existing portfolio? (yes/no): ").lower()
    
    if has_portfolio == 'yes':
        portfolio = {}
        while True:
            entry = console.input("Enter a stock ticker and quantity (e.g., TSLA 15), or 'done' to finish: ")
            if entry.lower() == 'done':
                break
            try:
                ticker, quantity = entry.split()
                portfolio[ticker.upper()] = int(quantity)
            except ValueError:
                console.print("Invalid format. Please use 'TICKER QUANTITY' (e.g., 'TSLA 15').")
        return portfolio
    else:
        console.print("Creating a standard portfolio.")
        return {
            "AAPL": 3333,
            "MSFT": 3333,
            "NVDA": 3333
        }

def get_capital():
    """
    Prompts the user to enter their available capital for deployment.
    """
    while True:
        try:
            capital = int(console.input("How much capital do you have for deployment? (1-1,000,000): "))
            if 1 <= capital <= 1_000_000:
                return capital
            else:
                console.print("Please enter an amount between 1 and 1,000,000.")
        except ValueError:
            console.print("Invalid input. Please enter a number.")

def get_risk_profile():
    """
    Displays a table of risk profiles and asks the user to select one.
    """
    table = Table(title="Risk Profiles")
    table.add_column("Lev.", style="cyan")
    table.add_column("Risk Profile", style="magenta")
    table.add_column("Typical Stock/Bond Style (Illustrative)")

    risk_profiles = [
        ("1", "Ultra conservative", "0–20% stocks, 80–100% high‑grade bonds/cash"),
        ("2", "Very conservative", "20–30% stocks, rest investment‑grade bonds"),
        ("3", "Conservative", "30–40% stocks, broad bond funds dominant"),
        ("4", "Mod. conservative", "40–50% stocks, 50–60% bonds"),
        ("5", "Balanced", "~60% stocks, 40% bonds (classic 60/40)"),
        ("6", "Mod. aggressive", "70–80% stocks, 20–30% bonds"),
        ("7", "Aggressive", "80–90% stocks, small bond/cash buffer"),
        ("8", "Very aggressive", "90–100% stocks, globally diversified"),
        ("9", "Speculative", "100% stocks, tilts to sectors/themes"),
        ("10", "Highly speculative", "100% stocks, heavy single‑stock / options"),
    ]

    for level, profile, style in risk_profiles:
        table.add_row(level, profile, style)

    console.print(table)

    while True:
        try:
            level = int(console.input("Please select your risk profile level (1-10): "))
            if 1 <= level <= 10:
                return level
            else:
                console.print("Please enter a level between 1 and 10.")
        except ValueError:
            console.print("Invalid input. Please enter a number.")

def get_tickers_to_research():
    """
    Prompts the user to choose between researching all tickers or a small subset.
    """
    while True:
        choice = console.input("Do you want to research all tickers (approx. 1000) or a small subset (AAPL, MSFT, NVDA)? (all/subset): ").lower()
        if choice in ['all', 'subset']:
            if choice == 'all':
                return TICKERS
            else:
                return ["AAPL", "MSFT", "NVDA"]
        else:
            console.print("Invalid input. Please enter 'all' or 'subset'.")

def get_backtesting_date():
    """
    Prompts the user to opt-in for backtesting and select a date.
    Returns the selected date string (YYYY-MM-DD) or None if disabled.
    """
    choice = console.input("Do you want to enable backtesting? (yes/no): ").lower()
    if choice == 'yes':
        while True:
            date_str = console.input("Enter the backtesting date (YYYY-MM-DD): ")
            try:
                datetime.strptime(date_str, '%Y-%m-%d')
                return date_str
            except ValueError:
                console.print("Invalid date format. Please use YYYY-MM-DD.")
    return None

def main():
    """
    Main function to run the financial agent.
    """
    console.print("--- Welcome to the Financial Agent ---", style="bold green")
    
    portfolio = get_portfolio()
    capital = get_capital()
    risk_profile = get_risk_profile()
    backtesting_date = get_backtesting_date()

    console.print("\n--- Your Configuration ---", style="bold green")
    console.print(f"Portfolio: {portfolio}")
    console.print(f"Capital: ${capital:,.2f}")
    console.print(f"Risk Profile Level: {risk_profile}")
    console.print(f"Backtesting Date: {backtesting_date if backtesting_date else 'Today'}")

    console.print("\n--- Starting Financial Analysis ---", style="bold green")
    
    tickers_to_research = get_tickers_to_research()
    console.print(f"Researching {len(tickers_to_research)} tickers...")
    research_output_json = run_research_agent(tickers_to_research)
    research_output = json.loads(research_output_json)
    financial_data = {res['financial_summary']['ticker']: FinancialSummary(**res['financial_summary']) for res in research_output.get('results', [])}
    console.print("Research complete.")

    # 2. Warren Buffett Agent (Run once)
    console.print("\n--- Running Warren Buffett Analysis ---", style="bold yellow")
    warren_buffett_signals = {}
    for ticker, summary in financial_data.items():
        signal_data = warren_buffett_agent(summary)
        if signal_data and ticker in signal_data:
            warren_buffett_signals.update(signal_data)
            reasoning = signal_data[ticker].get('reasoning', 'No reasoning provided.')
            signal = signal_data[ticker].get('signal', 'neutral')
            confidence = signal_data[ticker].get('confidence', 0)
            console.print(f"  - {ticker}: {signal.upper()} (Confidence: {confidence}%) - {reasoning}")
        else:
            console.print(f"  - {ticker}: Could not get analysis.")
    console.print("Warren Buffett analysis complete.")

    # Build Price Map
    console.print("\n--- Fetching Stock Prices ---", style="bold yellow")
    price_map = {}
    target_end_date = backtesting_date if backtesting_date else datetime.now().strftime('%Y-%m-%d')
    target_start_date = (datetime.strptime(target_end_date, '%Y-%m-%d') - timedelta(days=7)).strftime('%Y-%m-%d')

    for ticker in financial_data.keys():
        try:
            prices_data = get_stock_prices.func(
                ticker=ticker,
                start_date=target_start_date,
                end_date=target_end_date
            )
            if prices_data and 'prices' in prices_data and prices_data['prices']:
                price_map[ticker] = float(prices_data['prices'][-1]['close'])
            else:
                console.print(f"Warning: Could not fetch price for {ticker}")
                price_map[ticker] = 0.0
        except Exception as e:
            console.print(f"Error fetching price for {ticker}: {e}")
            price_map[ticker] = 0.0
    console.print(f"Prices fetched: {price_map}")

    # Main loop for 10 iterations
    for i in range(1, 11):
        console.print(f"\n--- Iteration {i}/10 ---", style="bold yellow")

        # 3. Portfolio Manager Agent
        console.print("Running Portfolio Manager...")
        pm_output = run_portfolio_manager_agent(
            portfolio, capital, risk_profile, warren_buffett_signals, price_map
        )
        proposed_trades = pm_output.get("proposed_trades", [])
        console.print(f"Proposed trades: {proposed_trades}")

        if not proposed_trades:
            console.print("No trades proposed. Ending iteration.")
            continue

        # 4. Monitor Agent (Check constraints)
        console.print("Running Monitor Agent...")
        monitor_output = run_monitor_agent(proposed_trades, portfolio, capital, price_map)
        is_valid = monitor_output.get("is_valid", False)
        violations = monitor_output.get("violations", [])
        console.print(f"Monitor result: Valid={is_valid}")
        if violations:
            console.print(f"Violations: {violations}")
        
        if not is_valid:
            console.print("Invalid trades. Skipping portfolio update.")
            continue

        # 5. What If Agent (Simulate)
        console.print("Running What If Agent...")
        what_if_output = run_what_if_agent(portfolio, capital, proposed_trades, price_map, warren_buffett_signals)
        
        # Update portfolio and capital based on simulation
        # In a real agent loop, the Portfolio Manager might refine based on What-If feedback.
        # Here we accept the valid trades and update the state for the next iteration.
        if "after" in what_if_output:
            portfolio = what_if_output["after"].get("portfolio", portfolio)
            capital = what_if_output["after"].get("cash", capital)
            console.print("Portfolio and Capital updated based on simulation.")

        console.print(f"--- End of Iteration {i}/10 ---", style="bold yellow")
        console.print(f"New Portfolio: {portfolio}")
        console.print(f"Remaining Capital: ${capital:,.2f}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        console.print(f"An error occurred: {e}", style="bold red")
