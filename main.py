#%%
from ai_agents.research_agent import run_research_agent
from ai_agents.analysis_agent import run_analysis_agent


# 1. Esegui il Research Agent (recupero + sintesi dati)
summary = run_research_agent("TSLA")

# 2. Esegui l'Analysis Agent (commento analitico)
answer = run_analysis_agent(
    summary,
    "Mi fai un commento sul rischio/rendimento?"
)

# 3. Output finale
print("\n=== RISPOSTA FINALE ===\n")
print(answer)