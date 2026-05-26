"""Trading calendar derived from the cached price series.

Sessions are the sorted union of price dates across the universe ∪ SPY, so
weekends and market holidays are absent by construction — no external calendar
dependency. Per-ticker gaps are handled by forward-fill in the cache's
``close_on`` (used for mark-to-market).
"""

from __future__ import annotations

import bisect

from .data_cache import PiTDataCache


class TradingCalendar:
    def __init__(self, cache: PiTDataCache):
        self._dates: list[str] = cache.all_trading_dates()

    def sessions(self, start: str, end: str) -> list[str]:
        """All trading sessions in the inclusive [start, end] window."""
        lo = bisect.bisect_left(self._dates, start)
        hi = bisect.bisect_right(self._dates, end)
        return self._dates[lo:hi]

    def is_session(self, date: str) -> bool:
        i = bisect.bisect_left(self._dates, date)
        return i < len(self._dates) and self._dates[i] == date

    def next_session(self, date: str) -> str | None:
        """First session strictly after ``date`` (used for next-open fills)."""
        i = bisect.bisect_right(self._dates, date)
        return self._dates[i] if i < len(self._dates) else None

    def prev_session(self, date: str) -> str | None:
        i = bisect.bisect_left(self._dates, date)
        return self._dates[i - 1] if i > 0 else None

    @property
    def all_dates(self) -> list[str]:
        return list(self._dates)
