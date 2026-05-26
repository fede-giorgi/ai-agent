"""
Central configuration for the AI Hedge Fund simulation.

All magic numbers and tunable constants live here so callers
never hard-code values that may need changing across runs.
"""

# ── Pipeline ──────────────────────────────────────────────────────────────────

# Number of PM → Monitor → What-If debate iterations
TOTAL_ITERATIONS: int = 10
TOTAL_ITERATIONS_DEBUG: int = 3

# Tickers used in --debug mode and as the "default" preset
DEFAULT_TICKERS: list[str] = ["AAPL", "MSFT", "NVDA", "GOOGL", "META"]

# ── Backtesting benchmarks ────────────────────────────────────────────────────

# US 3-month T-bill rate used as the risk-free benchmark.
# Update periodically; current Fed funds / T-bill environment: ~4.5%.
RISK_FREE_ANNUAL: float = 0.045

# ── LLM model tiers (Amazon Bedrock Claude) ─────────────────────────────────
# Cross-region inference-profile ids. CONFIRM exact ids for your account/region:
#   aws bedrock list-inference-profiles --region us-east-2
BEDROCK_REGION: str = "us-east-2"

# High-volume workhorse: research tool loops, PM, Monitor, What-If, history compression.
WORKHORSE_MODEL: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

# Quality-critical, low-volume: Warren Buffett signal + Final Orchestrator.
# TODO: confirm the exact Sonnet 4.6 date stamp via list-inference-profiles.
JUDGE_MODEL: str = "us.anthropic.claude-sonnet-4-6-20250929-v1:0"
