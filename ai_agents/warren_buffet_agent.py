"""
This script defines an investment agent that analyzes stocks according to Warren Buffett's value investing principles.
"""
from langchain.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage

import math
import json

from models.financial_summary import FinancialSummary, WarrenBuffettSignal
from llm import get_llm

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

    structured_llm = llm.with_structured_output(WarrenBuffettSignal)

    system_instruction = SystemMessage(content="""You are a virtual Warren Buffett. Your goal is to evaluate a company based on value investing principles and provide a final investment signal.

    Key Questions to Answer:
    - Is the business understandable and within a circle of competence? (Assume yes).
    - Does it have a durable competitive advantage (moat)?
    - Is the management rational and shareholder-friendly?
    - Is the company financially strong?
    - Is the stock trading at a significant discount to its intrinsic value?

    Instructions:
    - Based strictly on the provided analysis data, determine a bullish, bearish, or neutral signal.
    - Assign a confidence score (0-100).
    - Provide a brief, decisive reasoning.""")
            
    user_content = HumanMessage(content=f"""Here is the quantitative analysis for {summary.ticker}:{json.dumps(analysis_results, indent=2)}
    Please generate the investment signal now.""")
    
    final_signal = structured_llm.invoke([system_instruction, user_content])
    
    return {summary.ticker: final_signal.model_dump()}
