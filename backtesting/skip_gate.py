"""Day-level skip gate (deterministic, no LLM).

Most of what makes a daily 3-month backtest tractable: only re-run the full agent
pipeline when something the agent could act on has actually changed since the last
run — a material price move, a new filing/news item/financial report crossing the
cutoff, or a max-days cadence. On a skipped day the harness only marks-to-market.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from . import config
from .data_cache import PiTDataCache


def _max_date_leq(rows: list[dict], field_name: str, cutoff: str) -> str:
    best = ""
    for r in rows:
        d = r.get(field_name, "")
        if d and d <= cutoff and d > best:
            best = d
    return best


def _latest_filing(cache, t, cutoff):
    return _max_date_leq(cache.raw(t, "insider").get("insider_trades", []), "filing_date", cutoff)


def _latest_news(cache, t, cutoff):
    return _max_date_leq(cache.raw(t, "news").get("news", []), "date", cutoff)


def _latest_report(cache, t, cutoff):
    return _max_date_leq(cache.raw(t, "financials").get("income_statements", []), "report_period", cutoff)


@dataclass
class LastRunSnapshot:
    date: str
    prices: dict[str, float] = field(default_factory=dict)
    max_filing: dict[str, str] = field(default_factory=dict)
    max_news: dict[str, str] = field(default_factory=dict)
    max_report: dict[str, str] = field(default_factory=dict)


def build_snapshot(date: str, cache: PiTDataCache, universe: list[str]) -> LastRunSnapshot:
    return LastRunSnapshot(
        date=date,
        prices={t: (cache.close_on(t, date) or 0.0) for t in universe},
        max_filing={t: _latest_filing(cache, t, date) for t in universe},
        max_news={t: _latest_news(cache, t, date) for t in universe},
        max_report={t: _latest_report(cache, t, date) for t in universe},
    )


class SkipGate:
    def __init__(self,
                 price_move_pct: float = config.GATE_PRICE_MOVE_PCT,
                 max_days_between: int = config.GATE_MAX_DAYS_BETWEEN_RUNS,
                 force_first_day: bool = config.GATE_FORCE_FIRST_DAY):
        self.price_move_pct = price_move_pct
        self.max_days_between = max_days_between
        self.force_first_day = force_first_day

    def should_run(self, date: str, snapshot: LastRunSnapshot | None,
                   cache: PiTDataCache, universe: list[str]) -> tuple[bool, str]:
        if snapshot is None:
            return (True, "first_day") if self.force_first_day else (True, "no_snapshot")

        days = (datetime.strptime(date, "%Y-%m-%d") - datetime.strptime(snapshot.date, "%Y-%m-%d")).days
        if days >= self.max_days_between:
            return True, "cadence"

        for t in universe:
            c0 = snapshot.prices.get(t, 0.0)
            c1 = cache.close_on(t, date) or 0.0
            if c0 and c1 and abs(c1 - c0) / c0 >= self.price_move_pct:
                return True, f"price_move:{t}"

        for t in universe:
            if _latest_filing(cache, t, date) > snapshot.max_filing.get(t, ""):
                return True, f"new_filing:{t}"
            if _latest_news(cache, t, date) > snapshot.max_news.get(t, ""):
                return True, f"new_news:{t}"
            if _latest_report(cache, t, date) > snapshot.max_report.get(t, ""):
                return True, f"new_financials:{t}"

        return False, "no_trigger"
