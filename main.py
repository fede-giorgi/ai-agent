#%%
from ai_agents.research_agent import run_research_agent
from ai_agents.analysis_agent import run_analysis_agent

summary = run_research_agent("TSLA")

answer = run_analysis_agent(
    summary,
    "Can you provide an analysis on risk and return?"
)

# 3. Final output
print("\n=== FINAL ANSWER ===\n")
print(answer)
# %%
