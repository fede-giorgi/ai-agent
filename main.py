import json
import sys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
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
    # Check for debug mode
    debug_mode = "--debug" in sys.argv

    console.print("--- Welcome to the Financial Agent ---", style="bold green")
    
    if debug_mode:
        console.print("[bold red]DEBUG MODE ENABLED[/bold red]")
        portfolio = {}
        capital = 500000
        risk_profile = 7
        backtesting_date = None
    else:
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
    
    if debug_mode:
        tickers_to_research = ["AAPL", "MSFT", "NVDA"]
    else:
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

    # Build Price Map from Financial Data
    # Prices are now fetched by the research agent and stored in FinancialSummary
    price_map = {
        ticker: data.price if data.price else 0.0 
        for ticker, data in financial_data.items()
    }
    
    console.print(f"Prices fetched: {price_map}")

    # Main loop for 10 iterations
    history = []
    for i in range(1, 11):
        console.rule(f"[bold yellow]Iteration {i}/10[/bold yellow]")

        # 1. Display Context (Signals & Current State)
        signals_text = Text()
        for ticker, signal_data in warren_buffett_signals.items():
            s = signal_data.get('signal', 'neutral').upper()
            c = signal_data.get('confidence', 0)
            color = "green" if s == "BULLISH" else "red" if s == "BEARISH" else "yellow"
            signals_text.append(f"- {ticker}: {s} (Confidence: {c}%)\n", style=color)
        
        console.print(Panel(signals_text, title="Warren Buffett Signals", expand=False))
        console.print(f"[bold]Current Portfolio:[/bold] {portfolio}")
        console.print(f"[bold]Available Capital:[/bold] ${capital:,.2f}")

        # 3. Portfolio Manager Agent
        console.print("\n[bold cyan]--- Portfolio Manager Agent ---[/bold cyan]")
        pm_output = run_portfolio_manager_agent(
            portfolio, capital, risk_profile, warren_buffett_signals, price_map
        )
        console.print_json(data=pm_output)
        
        proposed_trades = pm_output.get("proposed_trades", [])

        if not proposed_trades:
            console.print("[yellow]No trades proposed. Ending iteration.[/yellow]")
            history.append({"iteration": i, "status": "No Trades", "portfolio": portfolio.copy(), "capital": capital})
            continue

        # 4. Monitor Agent (Check constraints)
        console.print("\n[bold cyan]--- Monitor Agent ---[/bold cyan]")
        monitor_output = run_monitor_agent(proposed_trades, portfolio, capital, price_map)
        console.print_json(data=monitor_output)
        
        is_valid = monitor_output.get("is_valid", False)
        
        if not is_valid:
            console.print("[bold red]Invalid trades. Skipping portfolio update.[/bold red]")
            history.append({"iteration": i, "status": "Invalid", "portfolio": portfolio.copy(), "capital": capital})
            continue

        # 5. What If Agent (Simulate)
        console.print("\n[bold cyan]--- What If Agent ---[/bold cyan]")
        what_if_output = run_what_if_agent(portfolio, capital, proposed_trades, price_map, warren_buffett_signals)
        console.print_json(data=what_if_output)
        
        # Update portfolio and capital based on simulation
        # In a real agent loop, the Portfolio Manager might refine based on What-If feedback.
        # Here we accept the valid trades and update the state for the next iteration.
        if "after" in what_if_output:
            portfolio = what_if_output["after"].get("portfolio", portfolio)
            capital = what_if_output["after"].get("cash", capital)
            console.print("[green]Portfolio and Capital updated based on simulation.[/green]")
            history.append({"iteration": i, "status": "Executed", "portfolio": portfolio.copy(), "capital": capital})

    # Final Summary
    console.rule("[bold green]Final Summary[/bold green]")
    console.print(Panel(signals_text, title="Warren Buffett Signals", expand=False))
    
    summary_table = Table(title="Iteration History")
    summary_table.add_column("Iter", justify="center")
    summary_table.add_column("Status", justify="center")
    summary_table.add_column("Resulting Portfolio", justify="left")
    summary_table.add_column("Capital", justify="right")
    
    for item in history:
        summary_table.add_row(
            str(item["iteration"]),
            f"[green]{item['status']}[/green]" if item["status"] == "Executed" else f"[red]{item['status']}[/red]",
            str(item["portfolio"]),
            f"${item['capital']:,.2f}"
        )
    
    console.print(summary_table)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        console.print(f"An error occurred: {e}", style="bold red")
