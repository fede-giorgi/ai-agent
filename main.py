#%%

from agents import run_financial_agent, run_analysis_agent
from agents import FinancialSummary

summary = run_financial_agent("TSLA")
answer = run_analysis_agent(summary, "Mi fai un commento sul rischio/rendimento?")

print("=== RISPOSTA FINALE ===")
print(answer)

# %%
