# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

**Agentic AI Hedge Fund** — an educational multi-agent system that simulates a hedge fund end-to-end. Specialized LLM agents handle data collection, value analysis, trade proposal, compliance validation, and a final decision, orchestrated **sequentially** via **LangChain**. It is plain Python (no web server); agents print live to the terminal via **Rich**.

A major restructure is in progress — see **`~/.claude/plans/snug-wandering-blanket.md`** and the project memory for locked decisions (Bedrock Claude tiered models, walk-forward backtest, point-in-time data cache, deterministic stopping). Read those before large changes.

## Commands

```bash
python main.py            # Interactive: prompts for capital, LLM, risk, backtest date, tickers
python main.py --debug    # Hardcoded $100k, risk 8, 90-day backtest, forces trades (fast smoke test)
pip install -r requirements.txt
```

**Environment (`.env`):**
- `FINDAT_API_KEY` — FinancialDatasets.ai (required; all 8 data tools)
- `LLM_PROVIDER` / `LLM_MODEL` — default provider/model (else falls back to Google)
- `GOOGLE_API_KEY` / `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` — per provider
- Bedrock (new): standard AWS creds + `BEDROCK_REGION` (default `us-east-2`); `BEDROCK_MAX_TOKENS` optional cap
- `LANGCHAIN_API_KEY` — optional LangSmith tracing (project `ai-hedge-fund`)

## Architecture

Pipeline is strictly sequential; each stage's output feeds the next (`main()` in `main.py`):

1. **Research Agent** (`ai_agents/research_agent.py`) — async, per ticker; `bind_tools` over the 8 FinancialDatasets tools; structures results into a `FinancialSummary`.
2. **Warren Buffett Agent** (`ai_agents/warren_buffet_agent.py`) — runs 8 analysis tools, emits a `WarrenBuffettSignal` (bullish/bearish/neutral + confidence 0–100).
3. **Trading debate loop** (`main.py`, ~`main.py:872`): per iteration runs **Portfolio Manager** (`portfolio_and_risk_manager.py`) → **Monitor** (`monitor.py`, deterministic `validate_trades`) → **What-If** (`what_if_agent.py`); appends to a `history` list.
4. **Final Orchestrator** (`final_orchestrator_agent.py`) — reviews `history` + signals, selects/synthesizes the final trades; trades are then executed and (optionally) backtested.

**LLM factory** — `llm.py:get_llm(provider, model)` returns a LangChain chat model for `google` / `anthropic` / `bedrock`. Every instance carries a shared `_TokenUsageCallback`; read totals via `get_usage_summary()`. Costs are in `_COST_PER_1M`. Model tiers live in `config.py` (`WORKHORSE_MODEL` = Haiku 4.5 for high-volume calls; `JUDGE_MODEL` = Sonnet 4.6 for analyst signal + orchestrator).

**Data models** (`classes/financial_summary.py`): `FinancialSummary` (~60 typed fields incl. multi-year arrays), `WarrenBuffettSignal`, `ResearchAgentOutput`/`Result`, `ToolStatus`.

**Tools** (`tools/`): 8 data tools wrapping `https://api.financialdatasets.ai/` (`get_financials`, `get_metrics`, `get_financial_line_items`, `get_stock_prices`, `get_company_news`, `get_segmented_revenues`, `get_insider_trades`, `get_analyst_estimates`) + 8 `analyze_*` / `calculate_*` analysis functions over `FinancialSummary`.

**Config** (`config.py`): iteration counts, `DEFAULT_TICKERS`, `RISK_FREE_ANNUAL`, model tiers.

## Critical Patterns

- **Buffett tools are no-arg closures.** Each analysis tool takes `summary: FinancialSummary`; passing that through LangChain's tool schema confuses the model. They're wrapped as no-arg closures over the ticker's summary (`warren_buffet_agent.py`). Preserve this when editing analysts.
- **Native tool-calling is required** (keeps the project agentic). On Bedrock this means **Claude** (or Mistral) — DeepSeek and Qwen3 do **not** support tool-use via the Converse API. Don't switch the workhorse to a model lacking Converse tool support.
- **Structured output** via Pydantic `with_structured_output`. `what_if_agent.py` and `final_orchestrator_agent.py` historically hand-parsed ```json``` strings — prefer structured output there.
- **Backtesting data leakage** is a known hazard: the legacy single-point backtest fetched prices without `end_date` (today's price) and had broken date filters. The restructure adds a **point-in-time cache** (`backtesting/`) that masks all data to `≤ cutoff`; agent-facing reads must never see the future. Mark-to-market/execution may use future prices (that's "the truth", not an agent input).
- **No persistent caching of API data yet** (being added in the restructure). Don't assume calls are memoized.

## Workflow Best Practices

- Start complex tasks in **plan mode**; keep this CLAUDE.md under ~200 lines.
- Use the **`brainstorming`** skill for design exploration, **`test-driven-development`** for new logic (especially the backtesting harness — write the no-leakage and buy-and-hold sanity tests first), **`lint-and-validate`** before finishing, and **`create-pr`** to open PRs.
- Work on **feature branches**, never commit directly to `main`. Open **proper PRs** to `origin` (`github.com/fede-giorgi/AI-Agent-Driven-Hedge-Fund`). Confirm with the user before pushing or opening a PR (outward-facing).
- Cost discipline: this project spends real AWS Bedrock credit. Use non-reasoning mode, cap `max_tokens`, and watch token usage; prefer `--debug` for smoke tests.

## Git Commit Rules

When committing, **create separate commits per file** — do not bundle multiple files into one commit. Each file gets its own commit with a message specific to that file's change. End commit messages with:

```
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```
