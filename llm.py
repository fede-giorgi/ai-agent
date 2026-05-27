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


class _TokenUsageCallback(BaseCallbackHandler):
    """Accumulates token usage across all LLM calls in a session."""

    def __init__(self):
        self._input_tokens = 0
        self._output_tokens = 0
        self._calls = 0
        self._model: str | None = None

    def on_llm_end(self, response: LLMResult, **kwargs):
        for gen_list in response.generations:
            for gen in gen_list:
                msg = getattr(gen, "message", None)
                if msg is not None:
                    meta = getattr(msg, "usage_metadata", None)
                    if meta:
                        self._input_tokens += meta.get("input_tokens", 0)
                        self._output_tokens += meta.get("output_tokens", 0)
                        self._calls += 1

    def summary(self, model: str | None = None) -> dict:
        m = model or self._model
        cost = None
        rates = _COST_PER_1M.get(m) if m else None
        if rates is None and m:
            # Bedrock profile ids are long (e.g. "us.anthropic.claude-haiku-4-5-...-v1:0");
            # match the longest pricing key that is a substring of the model id.
            candidates = [k for k in _COST_PER_1M if k in m]
            if candidates:
                rates = _COST_PER_1M[max(candidates, key=len)]
        if rates is not None:
            cost = (
                self._input_tokens  / 1_000_000 * rates["input"] +
                self._output_tokens / 1_000_000 * rates["output"]
            )
        return {
            "calls":         self._calls,
            "input_tokens":  self._input_tokens,
            "output_tokens": self._output_tokens,
            "total_tokens":  self._input_tokens + self._output_tokens,
            "estimated_cost_usd": cost,
            "model": m,
        }


# Module-level singleton — shared across all agents in a session
_tracker = _TokenUsageCallback()


def get_usage_summary(model: str | None = None) -> dict:
    """Returns aggregated token usage for the current session."""
    return _tracker.summary(model)


def format_usage_line(model: str | None = None) -> str:
    """One-line running token/cost view for live progress display."""
    u = _tracker.summary(model)
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
        _tracker._model = resolved_model
        return ChatAnthropic(model=resolved_model, temperature=0, max_retries=2,
                             callbacks=[_tracker])

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
        _tracker._model = resolved_model
        # Native Converse tool-calling + with_structured_output work for Claude.
        # Reasoning is OFF by default (opt-in via additional_model_request_fields) — keep it
        # off to control output-token cost.
        return ChatBedrockConverse(
            model=resolved_model,
            region_name=region,
            temperature=0,
            max_tokens=max_tokens,
            callbacks=[_tracker],
        )

    resolved_model = model or _GOOGLE_DEFAULT
    _tracker._model = resolved_model
    return ChatGoogleGenerativeAI(
        model=resolved_model,
        temperature=0,
        max_tokens=None,
        timeout=None,
        max_retries=2,
        callbacks=[_tracker],
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
