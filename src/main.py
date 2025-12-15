import sys
import os
import json
import argparse
from datetime import datetime
from dotenv import load_dotenv
from colorama import Fore, Style, init
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

# MAP Agents
from src.agents.decomposer import task_decomposer
from src.agents.predictor import predictor_agent
from src.agents.evaluator import evaluator_agent

# Original Agents
from src.agents.portfolio_manager import portfolio_management_agent
from src.agents.risk_manager import risk_management_agent
from src.graph.state import AgentState
from src.utils.display import print_trading_output
from src.utils.analysts import get_analyst_nodes
from src.utils.progress import progress
from src.cli.input import parse_cli_inputs

load_dotenv()
init(autoreset=True)

def parse_hedge_fund_response(response):
    """Parses a JSON string and returns a dictionary."""
    try:
        return json.loads(response)
    except Exception as e:
        print(f"Error parsing response: {e}")
        return None

def should_continue(state: AgentState):
    """
    MAP Conditional Logic: Conflict Monitoring.
    If the evaluator score is too low, we force a replan (return to decomposer).
    """
    eval_data = state.get("evaluator_output", {})
    score = eval_data.get("score", 0)
    recommendation = eval_data.get("recommendation", "PROCEED")

    if score < 0.4 or recommendation == "REPLAN":
        print(f"{Fore.RED} [MAP] Low confidence score ({score}). Re-planning strategy...")
        return "replan"
    return "proceed"

def create_workflow():
    workflow = StateGraph(AgentState)

  
    workflow.add_node("decomposer", task_decomposer)
    workflow.add_node("predictor", predictor_agent)
    workflow.add_node("evaluator", evaluator_agent)
    

    workflow.add_node("risk_management_agent", risk_management_agent)
    workflow.add_node("portfolio_manager", portfolio_management_agent)

    analyst_nodes = get_analyst_nodes()
    for analyst_key, (node_name, node_func) in analyst_nodes.items():
        
        def make_filtered_node(key=analyst_key, func=node_func):
            def filtered_node(state: AgentState):
                selected = state.get("decomposer_output", {}).get("priority_analysts", [])
                if key not in selected and len(selected) > 0:
                    return {"data": state["data"]} 
                return func(state)
            return filtered_node
        
        workflow.add_node(node_name, make_filtered_node())

  
    workflow.set_entry_point("decomposer")

    for analyst_key in analyst_nodes.keys():
        node_name = analyst_nodes[analyst_key][0]
        workflow.add_edge("decomposer", node_name)
        workflow.add_edge(node_name, "predictor")

    workflow.add_edge("predictor", "evaluator")

    workflow.add_conditional_edges(
        "evaluator",
        should_continue,
        {
            "replan": "decomposer",
            "proceed": "risk_management_agent"
        }
    )

    workflow.add_edge("risk_management_agent", "portfolio_manager")
    workflow.add_edge("portfolio_manager", END)

    return workflow

def run_hedge_fund(tickers, start_date, end_date, portfolio, model_name, model_provider, show_reasoning):
    progress.start()
    try:
        workflow = create_workflow()
        agent = workflow.compile()

        final_state = agent.invoke({
            "messages": [HumanMessage(content="Execute trading strategy.")],
            "data": {
                "tickers": tickers,
                "portfolio": portfolio,
                "start_date": start_date,
                "end_date": end_date,
                "analyst_signals": {},
            },
            "metadata": {
                "show_reasoning": show_reasoning,
                "model_name": model_name,
                "model_provider": model_provider,
            },
        })

        return {
            "decisions": parse_hedge_fund_response(final_state["messages"][-1].content),
            "analyst_signals": final_state["data"]["analyst_signals"],
        }
    finally:
        progress.stop()

if __name__ == "__main__":
    inputs = parse_cli_inputs(description="Run AI Hedge Fund with MAP Architecture")
    
    # Portfolio Initialization
    portfolio = {
        "cash": inputs.initial_cash,
        "margin_requirement": inputs.margin_requirement,
        "positions": {t: {"long": 0, "short": 0} for t in inputs.tickers},
    }

    result = run_hedge_fund(
        tickers=inputs.tickers,
        start_date=inputs.start_date,
        end_date=inputs.end_date,
        portfolio=portfolio,
        model_name=inputs.model_name,
        model_provider=inputs.model_provider,
        show_reasoning=inputs.show_reasoning
    )
    print_trading_output(result)