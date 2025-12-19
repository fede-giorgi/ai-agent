"""
This script defines an investment agent that analyzes stocks according to Warren Buffett's value investing principles.
"""
from langchain.tools import tool
from models.financial_summary import FinancialSummary, WarrenBuffettSignal
from llm import get_llm
import math
import json

from tools.analyze_book_value_growth import analyze_book_value_growth
from tools.analyze_consistency import analyze_consistency
from tools.analyze_fundamentals import analyze_fundamentals
from tools.analyze_management_quality import analyze_management_quality
from tools.analyze_moat import analyze_moat
from tools.analyze_pricing_power import analyze_pricing_power
from tools.calculate_intrinsic_value import calculate_intrinsic_value


def warren_buffett_agent(summary: FinancialSummary) -> dict:
    """
    Runs the Warren Buffett agent to analyze a stock.
    """
    print(f"Analyzing {summary.ticker} with Warren Buffett agent...")
    
    llm = get_llm()
    
    # The tools now use the provided summary object directly, avoiding redundant API calls.
    
    analysis_results = {
        "fundamentals": analyze_fundamentals.func(summary=summary),
        "consistency": analyze_consistency.func(summary=summary),
        "moat": analyze_moat.func(summary=summary),
        "management": analyze_management_quality.func(summary=summary),
        "book_value_growth": analyze_book_value_growth.func(summary=summary),
        "intrinsic_value": calculate_intrinsic_value.func(summary=summary),
        "pricing_power": analyze_pricing_power.func(summary=summary),
    }

    # The user wants an LLM to generate the final output, so I will format the analysis results
    # and pass them to an LLM with a structured output model.

    structured_llm = llm.with_structured_output(WarrenBuffettSignal)

    prompt = f"""
    You are a virtual Warren Buffett. Based on the following analysis, provide a final investment signal.

    Analysis for {summary.ticker}:
    {json.dumps(analysis_results, indent=2)}

    - Is the business understandable and within a circle of competence? (Assume yes for this analysis).
    - Does it have a durable competitive advantage (moat)?
    - Is the management rational and shareholder-friendly?
    - Is the company financially strong?
    - Is the stock trading at a significant discount to its intrinsic value?

    Based on the analysis, provide a bullish, bearish, or neutral signal, a confidence score (0-100), and a brief reasoning.
    """
    
    final_signal = structured_llm.invoke(prompt)
    
    return {summary.ticker: final_signal.model_dump()}
