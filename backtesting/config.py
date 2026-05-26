"""Configuration for the backtesting harness and point-in-time data cache."""

import os

from config import RISK_FREE_ANNUAL  # re-exported from the root config (risk-free benchmark)

__all__ = ["RISK_FREE_ANNUAL"]

# Where the downloaded full-window data is persisted (git-ignored).
CACHE_DIR: str = os.getenv("BT_CACHE_DIR", ".bt_cache")

# Market benchmark ticker.
SPY_TICKER: str = "SPY"

# A few extra calendar days before the window start so the first session has a
# prior close for returns / mark-to-market.
PRICE_LEAD_IN_DAYS: int = 10

# How many periods to pull for statement-style endpoints (we fetch wide, then mask).
FINANCIALS_LIMIT: int = 12
METRICS_LIMIT: int = 12
LINE_ITEMS_LIMIT: int = 16
NEWS_LIMIT: int = 100
INSIDER_LIMIT: int = 100
ESTIMATES_LIMIT: int = 8
SEGMENTED_LIMIT: int = 8

# Concurrency for the one-time bulk download (task: speed up data pulls).
MAX_FETCH_WORKERS: int = 12

# Broad default line-items set so the cache covers what the analysis tools read
# from FinancialSummary. (The /financials/search/line-items POST takes the whole
# universe in a single request.)
DEFAULT_LINE_ITEMS: list[str] = [
    "revenue",
    "net_income",
    "gross_profit",
    "operating_income",
    "free_cash_flow",
    "capital_expenditure",
    "outstanding_shares",
    "shareholders_equity",
    "total_debt",
    "total_assets",
    "current_assets",
    "current_liabilities",
    "dividends_and_other_cash_distributions",
    "earnings_per_share",
    "book_value_per_share",
    "operating_cash_flow",
]

# ── Walk-forward harness ────────────────────────────────────────────────────
INITIAL_CAPITAL: float = 100_000.0
RISK_PROFILE: int = 6

# Execution model
FILL_TIMING: str = "next_open"   # "next_open" (clean, no look-ahead) | "close"
SLIPPAGE_BPS: float = 0.0        # basis points applied against the fill
FRACTIONAL_SHARES: bool = False  # match production (integer shares)

# Day-level skip gate (deterministic, no LLM)
GATE_PRICE_MOVE_PCT: float = 0.03        # re-run if any name moved ≥3% since last run
GATE_MAX_DAYS_BETWEEN_RUNS: int = 5      # force a run at least weekly
GATE_FORCE_FIRST_DAY: bool = True

# Metrics
TRADING_DAYS_PER_YEAR: int = 252
