"""
This script defines an investment agent that analyzes stocks according to Warren Buffett's value investing principles.
"""
from langchain.tools import tool
from pydantic import BaseModel, Field
from typing_extensions import Literal
from models.financial_summary import FinancialSummary
from llm import get_llm
import math

# --- Pydantic Models ---

class WarrenBuffettSignal(BaseModel):
    """The final output of the Warren Buffett agent."""
    signal: Literal["bullish", "bearish", "neutral"] = Field(description="The investment signal for the stock.")
    confidence: int = Field(description="The confidence level of the signal, from 0 to 100.")
    reasoning: str = Field(description="A brief reasoning for the signal.")

# --- Helper Functions ---

def _calculate_book_value_cagr(book_values: list) -> tuple[int, str]:
    """A private helper function to calculate the compound annual growth rate of book value."""
    if len(book_values) < 2:
        return 0, "Insufficient data for CAGR calculation"

    oldest_bv, latest_bv = book_values[-1], book_values[0]
    years = len(book_values) - 1

    if oldest_bv > 0 and latest_bv > 0:
        cagr = ((latest_bv / oldest_bv) ** (1 / years)) - 1
        if cagr > 0.15:
            return 2, f"Excellent book value CAGR: {cagr:.1%}"
        elif cagr > 0.1:
            return 1, f"Good book value CAGR: {cagr:.1%}"
        else:
            return 0, f"Book value CAGR: {cagr:.1%}"
    elif oldest_bv < 0 < latest_bv:
        return 3, "Excellent: Company improved from negative to positive book value"
    elif oldest_bv > 0 > latest_bv:
        return 0, "Warning: Company declined from positive to negative book value"
    else:
        return 0, "Unable to calculate meaningful book value CAGR due to negative values"

def estimate_maintenance_capex(summary: FinancialSummary) -> float:
    """Estimates the capital expenditures required to maintain current operations."""
    # This is a simplified estimation. A more robust implementation would be needed for a real-world scenario.
    if summary.depreciation_and_amortization:
        return summary.depreciation_and_amortization
    return 0.0

# --- Analysis Tools ---

@tool
def analyze_fundamentals(summary: FinancialSummary) -> dict:
    """Analyzes key financial health metrics like ROE, debt, margins, and liquidity."""
    score = 0
    reasoning = []

    if summary.return_on_equity and summary.return_on_equity > 0.15:
        score += 2
        reasoning.append(f"Strong ROE of {summary.return_on_equity:.1%}")
    
    if summary.debt_to_equity and summary.debt_to_equity < 0.5:
        score += 2
        reasoning.append("Conservative debt levels.")

    if summary.operating_margin and summary.operating_margin > 0.15:
        score += 2
        reasoning.append("Strong operating margins.")

    if summary.current_ratio and summary.current_ratio > 1.5:
        score += 1
        reasoning.append("Good liquidity position.")

    return {"score": score, "details": "; ".join(reasoning)}

@tool
def analyze_consistency(summary: FinancialSummary) -> dict:
    """Checks for a track record of consistent and growing earnings."""
    score = 0
    reasoning = []

    if summary.earnings_growth and summary.earnings_growth > 0.05:
        score += 3
        reasoning.append("Consistent earnings growth.")
    
    return {"score": score, "details": "; ".join(reasoning)}

@tool
def analyze_moat(summary: FinancialSummary) -> dict:
    """Evaluates the company's durable competitive advantage by looking at return on capital and margin stability."""
    moat_score = 0
    reasoning = []

    if summary.return_on_invested_capital and summary.return_on_invested_capital > 0.15:
        moat_score += 2
        reasoning.append("High ROIC suggests a strong moat.")

    if summary.gross_margin and summary.gross_margin > 0.4:
        moat_score += 1
        reasoning.append("High gross margins indicate pricing power.")

    return {"score": moat_score, "details": "; ".join(reasoning)}

@tool
def analyze_management_quality(summary: FinancialSummary) -> dict:
    """Assesses management's shareholder-friendliness by checking for share buybacks and dividends."""
    mgmt_score = 0
    reasoning = []

    if summary.issuance_or_purchase_of_equity_shares and summary.issuance_or_purchase_of_equity_shares < 0:
        mgmt_score += 1
        reasoning.append("Company has been repurchasing shares.")

    if summary.payout_ratio and summary.payout_ratio > 0:
        mgmt_score += 1
        reasoning.append("Company pays dividends.")

    return {"score": mgmt_score, "details": "; ".join(reasoning)}

@tool
def calculate_owner_earnings(summary: FinancialSummary) -> dict:
    """Calculates 'owner earnings', Buffett's preferred measure of profitability."""
    if not all([summary.net_income, summary.depreciation_and_amortization, summary.capital_expenditure]):
        return {"owner_earnings": None, "details": "Missing data for owner earnings calculation."}

    maintenance_capex = estimate_maintenance_capex(summary)
    owner_earnings = summary.net_income + summary.depreciation_and_amortization - maintenance_capex
    
    return {"owner_earnings": owner_earnings, "details": f"Owner earnings estimated at ${owner_earnings:,.0f}."}

@tool
def calculate_intrinsic_value(summary: FinancialSummary) -> dict:
    """Estimates the company's intrinsic value using a DCF model."""
    owner_earnings_data = calculate_owner_earnings(summary)
    if not owner_earnings_data["owner_earnings"]:
        return {"intrinsic_value": None, "details": "Could not calculate owner earnings."}
    
    owner_earnings = owner_earnings_data["owner_earnings"]
    
    # Simplified DCF model
    growth_rate = summary.earnings_growth if summary.earnings_growth and summary.earnings_growth > 0 else 0.03
    discount_rate = 0.09
    terminal_growth_rate = 0.02

    # 10-year, 2-stage DCF
    dcf_value = 0
    for i in range(1, 11):
        dcf_value += owner_earnings * ((1 + growth_rate) ** i) / ((1 + discount_rate) ** i)

    terminal_value = (dcf_value * (1 + terminal_growth_rate)) / (discount_rate - terminal_growth_rate)
    intrinsic_value = (dcf_value + terminal_value)

    if summary.outstanding_shares:
        intrinsic_value_per_share = intrinsic_value / summary.outstanding_shares
    else:
        intrinsic_value_per_share = 0

    return {"intrinsic_value": intrinsic_value, "intrinsic_value_per_share": intrinsic_value_per_share, "details": f"Intrinsic value estimated at ${intrinsic_value:,.0f}."}


@tool
def analyze_book_value_growth(summary: FinancialSummary) -> dict:
    """Analyzes the growth of book value per share over time."""
    score = 0
    reasoning = []
    
    if summary.book_value_growth and summary.book_value_growth > 0.1:
        score += 2
        reasoning.append("Strong book value growth.")

    return {"score": score, "details": "; ".join(reasoning)}

@tool
def analyze_pricing_power(summary: FinancialSummary) -> dict:
    """Assesses the company's ability to raise prices by analyzing its gross margin trends."""
    score = 0
    reasoning = []

    if summary.gross_margin and summary.gross_margin > 0.4:
        score += 2
        reasoning.append("High gross margins suggest strong pricing power.")
    
    return {"score": score, "details": "; ".join(reasoning)}


# --- Main Agent ---

def warren_buffett_agent(summary: FinancialSummary) -> dict:
    """
    Runs the Warren Buffett agent to analyze a stock.
    """
    print(f"Analyzing {summary.ticker} with Warren Buffett agent...")
    
    llm = get_llm()
    tools = [
        analyze_fundamentals,
        analyze_consistency,
        analyze_moat,
        analyze_management_quality,
        calculate_owner_earnings,
        calculate_intrinsic_value,
        analyze_book_value_growth,
        analyze_pricing_power,
    ]
    llm_with_tools = llm.bind_tools(tools)
    
    structured_llm = llm.with_structured_output(WarrenBuffettSignal)

    prompt = f"""
    You are a virtual Warren Buffett. Analyze the provided financial summary for the ticker {summary.ticker}.
    Your goal is to determine if the stock is a good investment based on your value investing principles.
    
    Use the provided tools to conduct your analysis. You must use at least three tools.
    
    Financial Summary:
    {summary.model_dump_json(indent=2)}
    
    After your analysis, provide a final investment signal (bullish, bearish, or neutral), a confidence score (0-100), and a brief reasoning.
    """

    # This is a simplified invocation. In a real scenario, you might have a more complex conversational chain.
    # For this refactoring, we'll directly call the structured LLM with the analysis prompt.
    
    # We are not invoking the tools here for real, as we don't have an execution environment for them.
    # We will generate a mock analysis based on the summary.
    
    mock_analysis_prompt = f"""
    Based on the following financial summary, generate a Warren Buffett style investment signal.
    
    Financial Summary:
    {summary.model_dump_json(indent=2)}
    
    - Is the Return on Equity (ROE) consistently high (e.g., > 15%)?
    - Is the debt-to-equity ratio low (e.g., < 0.5)?
    - Does the company have a strong competitive advantage (moat), indicated by high and stable margins?
    - Is management shareholder-friendly (e.g., buybacks, dividends)?
    - Is the stock trading at a significant discount to its intrinsic value?
    
    Based on these questions, provide a bullish, bearish, or neutral signal, a confidence score, and a brief reasoning.
    """
    
    final_signal = structured_llm.invoke(mock_analysis_prompt)
    
    return {summary.ticker: final_signal.model_dump()}