import os
import logging
import warnings
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

# Suppress langchain_google_genai "Both GOOGLE_API_KEY and GEMINI_API_KEY are set" noise
logging.getLogger("langchain_google_genai").setLevel(logging.ERROR)
logging.getLogger("langchain_google_genai.chat_models").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message=".*GOOGLE_API_KEY.*")
warnings.filterwarnings("ignore", message=".*GEMINI_API_KEY.*")
warnings.filterwarnings("ignore", message=".*pydantic.v1.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pydantic")

load_dotenv()

# ── LangSmith tracing (opt-in via env var) ────────────────────────────────────
if os.getenv("LANGCHAIN_API_KEY"):
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", "ai-hedge-fund")

_GOOGLE_DEFAULT = "gemini-3.1-pro-preview"
_ANTHROPIC_DEFAULT = "claude-opus-4-6"
# Bedrock cross-region inference-profile id. CONFIRM exact ids via:
#   aws bedrock list-inference-profiles --region us-east-2
_BEDROCK_DEFAULT = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

# Approximate cost per 1M tokens — update as pricing changes.
# Claude rates are Amazon Bedrock (us-east-2); `cache_read` is the prompt-cache
# hit rate for input tokens. Keys are matched against the model id by longest
# substring, so Bedrock inference-profile ids (e.g.
# "us.anthropic.claude-haiku-4-5-...-v1:0") resolve to the right family.
_COST_PER_1M: dict[str, dict[str, float]] = {
    "gemini-2.5-flash":       {"input": 0.075, "output": 0.30},
    "gemini-3.1-pro-preview": {"input": 1.25,  "output": 5.00},
    "claude-opus-4-7":        {"input": 5.50, "output": 27.50, "cache_read": 0.55},
    "claude-sonnet-4-6":      {"input": 3.30, "output": 16.50, "cache_read": 0.33},
    "claude-haiku-4-5":       {"input": 1.10, "output": 5.50,  "cache_read": 0.11},
}


def _rates_for(model: str | None) -> dict[str, float] | None:
    """Resolve pricing for a model id. Bedrock inference-profile ids are long
    (e.g. "us.anthropic.claude-haiku-4-5-...-v1:0"), so match the longest pricing
    key that is a substring of the id."""
    if not model:
        return None
    if model in _COST_PER_1M:
        return _COST_PER_1M[model]
    candidates = [k for k in _COST_PER_1M if k in model]
    return _COST_PER_1M[max(candidates, key=len)] if candidates else None


class _UsageAggregator:
    """Accumulates token usage **per model** across a session.

    A tiered run mixes the Haiku workhorse with the Sonnet judge; pricing every
    token at a single rate (whichever model was created last) over-states the
    bill — e.g. costing all tokens at Sonnet's rate when most calls were Haiku.
    Bucketing by model lets each tier be priced at its own rate.
    """

    def __init__(self):
        self._by_model: dict[str, dict[str, int]] = {}

    def record(self, model: str | None, input_tokens: int, output_tokens: int) -> None:
        bucket = self._by_model.setdefault(
            model or "unknown", {"input": 0, "output": 0, "calls": 0})
        bucket["input"] += input_tokens
        bucket["output"] += output_tokens
        bucket["calls"] += 1

    def summary(self, model: str | None = None) -> dict:
        # `model` is accepted for backward compatibility but no longer needed for
        # costing — each tier is now priced from its own bucket.
        in_tok = out_tok = calls = 0
        cost = 0.0
        cost_known = False
        for m, b in self._by_model.items():
            in_tok += b["input"]
            out_tok += b["output"]
            calls += b["calls"]
            rates = _rates_for(m)
            if rates is not None:
                cost += (b["input"]  / 1_000_000 * rates["input"] +
                         b["output"] / 1_000_000 * rates["output"])
                cost_known = True
        return {
            "calls":         calls,
            "input_tokens":  in_tok,
            "output_tokens": out_tok,
            "total_tokens":  in_tok + out_tok,
            "estimated_cost_usd": cost if cost_known else None,
            "model": model or ", ".join(sorted(self._by_model)) or None,
            "by_model": {m: dict(b) for m, b in self._by_model.items()},
        }


class _TokenUsageCallback(BaseCallbackHandler):
    """Per-LLM callback that records each call's tokens against its own model id
    in the shared aggregator. One instance is attached per ``get_llm()`` so the
    Haiku and Sonnet tiers stay distinct in the accounting."""

    def __init__(self, aggregator: "_UsageAggregator", model: str | None):
        self._aggregator = aggregator
        self._model = model

    def on_llm_end(self, response: LLMResult, **kwargs):
        for gen_list in response.generations:
            for gen in gen_list:
                msg = getattr(gen, "message", None)
                if msg is not None:
                    meta = getattr(msg, "usage_metadata", None)
                    if meta:
                        self._aggregator.record(
                            self._model,
                            meta.get("input_tokens", 0),
                            meta.get("output_tokens", 0),
                        )


# Module-level singleton aggregator — shared across all agents in a session.
_aggregator = _UsageAggregator()


def get_usage_summary(model: str | None = None) -> dict:
    """Returns aggregated token usage (priced per model tier) for the session."""
    return _aggregator.summary(model)


def format_usage_line(model: str | None = None) -> str:
    """One-line running token/cost view for live progress display."""
    u = _aggregator.summary(model)
    cost = u["estimated_cost_usd"]
    cost_s = f"~${cost:.4f}" if cost is not None else "cost n/a"
    return (f"{u['input_tokens']:,} in / {u['output_tokens']:,} out tok | "
            f"{u['calls']} calls | {cost_s}")


def get_llm(provider: str | None = None, model: str | None = None):
    """
    Returns an LLM instance for the requested provider and model.

    Reads LLM_PROVIDER and LLM_MODEL from the environment when the caller
    does not pass explicit values.  Defaults to Google Gemini.

    Attaches a token-usage callback to every returned LLM so that
    get_usage_summary() reflects the full session cost.

    Args:
        provider: "google" or "anthropic". Falls back to $LLM_PROVIDER, then "google".
        model: Model name string. Falls back to $LLM_MODEL, then the provider default.

    Returns:
        A LangChain chat model instance (ChatGoogleGenerativeAI or ChatAnthropic).

    Raises:
        ImportError: If langchain-anthropic is not installed when provider is "anthropic".
    """
    provider = provider or os.getenv("LLM_PROVIDER", "google")
    model = model or os.getenv("LLM_MODEL")

    if provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise ImportError(
                "langchain-anthropic is required for Anthropic support. "
                "Install it with: pip install langchain-anthropic"
            ) from exc
        resolved_model = model or _ANTHROPIC_DEFAULT
        return ChatAnthropic(model=resolved_model, temperature=0, max_retries=2,
                             callbacks=[_TokenUsageCallback(_aggregator, resolved_model)])

    if provider == "bedrock":
        try:
            from langchain_aws import ChatBedrockConverse
        except ImportError as exc:
            raise ImportError(
                "langchain-aws is required for Amazon Bedrock support. "
                "Install it with: pip install langchain-aws boto3"
            ) from exc
        resolved_model = model or _BEDROCK_DEFAULT
        region = os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION", "us-east-2")
        max_tokens = int(os.getenv("BEDROCK_MAX_TOKENS", "8192"))
        # Native Converse tool-calling + with_structured_output work for Claude.
        # Reasoning is OFF by default (opt-in via additional_model_request_fields) — keep it
        # off to control output-token cost.
        return ChatBedrockConverse(
            model=resolved_model,
            region_name=region,
            temperature=0,
            max_tokens=max_tokens,
            callbacks=[_TokenUsageCallback(_aggregator, resolved_model)],
        )

    resolved_model = model or _GOOGLE_DEFAULT
    return ChatGoogleGenerativeAI(
        model=resolved_model,
        temperature=0,
        max_tokens=None,
        timeout=None,
        max_retries=2,
        callbacks=[_TokenUsageCallback(_aggregator, resolved_model)],
    )


def get_judge_llm():
    """LLM for quality-critical, low-volume calls (Warren Buffett signal, Final Orchestrator).

    On Amazon Bedrock this returns the Sonnet "judge" tier (``config.JUDGE_MODEL``).
    On other providers there is no separate tier, so it falls back to the standard
    provider default. High-volume "workhorse" agents simply call ``get_llm()``, which
    on Bedrock defaults to Haiku (``_BEDROCK_DEFAULT``) — so leave ``LLM_MODEL`` unset
    on Bedrock to keep the tiers distinct.
    """
    if os.getenv("LLM_PROVIDER", "google") == "bedrock":
        from config import JUDGE_MODEL
        return get_llm("bedrock", JUDGE_MODEL)
    return get_llm()
