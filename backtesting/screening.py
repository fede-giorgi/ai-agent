"""Deterministic universe screening — the large-universe cost lever.

Before the expensive per-ticker LLM analysis runs, rank a big universe on cheap
cached fundamentals + price momentum (all as-of the cutoff, no look-ahead) and
keep only the top-K candidates. This keeps token cost ~flat in universe size:
1000 names → screen → ~10 analyzed. Pure function over the cache → unit-tested.

Composite = w_quality·z(ROE) + w_value·z(earnings yield) + w_momentum·z(return),
where z is the cross-sectional z-score (missing features score 0).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .as_of_provider import AsOfProvider
from .data_cache import PiTDataCache

DEFAULT_WEIGHTS = {"quality": 1.0, "value": 1.0, "momentum": 1.0}
MOMENTUM_LOOKBACK_DAYS = 90


def _latest_metric(provider: AsOfProvider, ticker: str, field: str) -> float | None:
    rows = provider.get_metrics(ticker).get("financial_metrics", [])
    if not rows:
        return None
    latest = max(rows, key=lambda r: r.get("report_period", ""))
    v = latest.get(field)
    return float(v) if isinstance(v, (int, float)) else None


def _momentum(cache: PiTDataCache, ticker: str, cutoff: str,
              lookback_days: int = MOMENTUM_LOOKBACK_DAYS) -> float | None:
    c1 = cache.close_on(ticker, cutoff)
    past = (datetime.strptime(cutoff, "%Y-%m-%d") - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    c0 = cache.close_on(ticker, past)
    return (c1 / c0 - 1.0) if (c0 and c1 and c0 > 0) else None


def _zscores(values: dict[str, float | None]) -> dict[str, float]:
    present = [v for v in values.values() if v is not None]
    if len(present) < 2:
        return {k: 0.0 for k in values}
    mean = sum(present) / len(present)
    sd = (sum((v - mean) ** 2 for v in present) / (len(present) - 1)) ** 0.5
    return {k: ((v - mean) / sd if (v is not None and sd > 0) else 0.0) for k, v in values.items()}


def screen_universe(cache: PiTDataCache, tickers: list[str], cutoff: str,
                    top_k: int | None = None, weights: dict | None = None) -> list[str]:
    """Return ``tickers`` ranked best-first; truncated to ``top_k`` if given."""
    weights = weights or DEFAULT_WEIGHTS
    provider = AsOfProvider(cache, cutoff)

    roe = {t: _latest_metric(provider, t, "return_on_equity") for t in tickers}
    pe = {t: _latest_metric(provider, t, "price_to_earnings_ratio") for t in tickers}
    earnings_yield = {t: (1.0 / pe[t] if (pe[t] and pe[t] > 0) else None) for t in tickers}
    momentum = {t: _momentum(cache, t, cutoff) for t in tickers}

    zq, zv, zm = _zscores(roe), _zscores(earnings_yield), _zscores(momentum)
    score = {t: weights["quality"] * zq[t] + weights["value"] * zv[t] + weights["momentum"] * zm[t]
             for t in tickers}

    ranked = sorted(tickers, key=lambda t: (score[t], t), reverse=True)
    return ranked[:top_k] if top_k else ranked
