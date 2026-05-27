"""Small async helpers shared across agents."""

from __future__ import annotations

import asyncio
from typing import Awaitable, TypeVar

T = TypeVar("T")


async def bounded_gather(*awaitables: Awaitable[T], limit: int,
                         return_exceptions: bool = False) -> list:
    """Like ``asyncio.gather`` but with at most ``limit`` awaitables in flight.

    The per-ticker analyst calls fan out with ``gather``; unbounded, that fires
    *every* call at once. Fine for a handful of tickers, but once a screened
    universe is large it trips Amazon Bedrock's per-minute throttling and fails
    the run. A semaphore caps the fan-out while still running small universes
    fully in parallel. Results preserve input order, exactly like ``gather``.

    ``limit <= 0`` means no cap (plain ``gather``).
    """
    if limit <= 0:
        return await asyncio.gather(*awaitables, return_exceptions=return_exceptions)

    sem = asyncio.Semaphore(limit)

    async def _run(aw: Awaitable[T]) -> T:
        async with sem:
            return await aw

    return await asyncio.gather(*(_run(aw) for aw in awaitables),
                                return_exceptions=return_exceptions)
