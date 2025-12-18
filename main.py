import json
from rich.console import Console
from rich.table import Table

from ai_agents.research_agent import run_research_agent
from ai_agents.warren_buffet_agent import warren_buffett_agent
from ai_agents.portfolio_manager import run_portfolio_manager_agent
from ai_agents.what_if_agent import run_what_if_agent
from ai_agents.monitor import run_monitor_agent
from ai_agents.tickers import TICKERS

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

def main():
    """
    Main function to run the financial agent.
    """
    console.print("--- Welcome to the Financial Agent ---", style="bold green")
    
    portfolio = get_portfolio()
    capital = get_capital()
    risk_profile = get_risk_profile()

    console.print("\n--- Your Configuration ---", style="bold green")
    console.print(f"Portfolio: {portfolio}")
    console.print(f"Capital: ${capital:,.2f}")
    console.print(f"Risk Profile Level: {risk_profile}")

    console.print("\n--- Starting Financial Analysis ---", style="bold green")
    
    tickers_to_research = get_tickers_to_research()
    console.print(f"Researching {len(tickers_to_research)} tickers...")
    financial_data_list = run_research_agent(tickers_to_research)
    financial_data = {summary.ticker: summary for summary in financial_data_list}
    console.print("Research complete.")

    # Main loop for 10 iterations
    for i in range(1, 11):
        console.print(f"\n--- Iteration {i}/10 ---", style="bold yellow")

        # 2. Warren Buffett Agent
        console.print("Running Warren Buffett analysis...")
        warren_buffett_signals = {}
        for ticker, summary in financial_data.items():
            signal = warren_buffett_agent(summary)
            warren_buffett_signals.update(signal)
        console.print("Warren Buffett analysis complete.")

        # 3. Portfolio Manager Agent
        console.print("Running Portfolio Manager...")
        proposed_trades = run_portfolio_manager_agent(
            portfolio, warren_buffett_signals, risk_profile, capital, financial_data
        )
        console.print(f"Proposed trades: {proposed_trades}")

        if not proposed_trades:
            console.print("No trades proposed. Ending iteration.")
            continue

        # 4. Monitor Agent
        console.print("Running Monitor Agent...")
        is_valid, message = run_monitor_agent(proposed_trades, capital, financial_data)
        console.print(f"Monitor result: {message}")
        
        if not is_valid:
            console.print("Invalid trades. Skipping portfolio update.")
            continue

        # 5. What If Agent
        console.print("Running What If Agent...")
        new_portfolio_json = run_what_if_agent(portfolio, proposed_trades)
        portfolio = json.loads(new_portfolio_json)
        
        # Update capital
        # This is a simplification. A real system would track cash more accurately.
        for trade in proposed_trades:
            if trade['action'] == 'buy':
                price = financial_data[trade['ticker']].market_cap / financial_data[trade['ticker']].outstanding_shares if financial_data[trade['ticker']].outstanding_shares else 0
                capital -= trade['shares'] * price
            elif trade['action'] == 'sell':
                price = financial_data[trade['ticker']].market_cap / financial_data[trade['ticker']].outstanding_shares if financial_data[trade['ticker']].outstanding_shares else 0
                capital += trade['shares'] * price


        console.print(f"--- End of Iteration {i}/10 ---", style="bold yellow")
        console.print(f"New Portfolio: {portfolio}")
        console.print(f"Remaining Capital: ${capital:,.2f}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        console.print(f"An error occurred: {e}", style="bold red")
