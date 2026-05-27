"""bounded_gather: capped-concurrency fan-out for per-ticker analyst calls.

Why it exists: unbounded asyncio.gather over a large screened universe fires
every Bedrock call at once and trips per-minute throttling. bounded_gather caps
in-flight calls while preserving gather's order/semantics.
"""

import asyncio

from async_utils import bounded_gather


def test_caps_concurrency_and_preserves_order():
    state = {"cur": 0, "max": 0}

    async def work(i):
        state["cur"] += 1
        state["max"] = max(state["max"], state["cur"])
        await asyncio.sleep(0.01)  # hold the slot so overlap is observable
        state["cur"] -= 1
        return i * 10

    out = asyncio.run(_gather(work, n=6, limit=2))
    assert out == [0, 10, 20, 30, 40, 50]   # order matches inputs
    assert state["max"] <= 2                # never more than `limit` in flight


def test_nonpositive_limit_is_unbounded():
    state = {"cur": 0, "max": 0}

    async def work(i):
        state["cur"] += 1
        state["max"] = max(state["max"], state["cur"])
        await asyncio.sleep(0.01)
        state["cur"] -= 1
        return i

    out = asyncio.run(_gather(work, n=5, limit=0))
    assert out == [0, 1, 2, 3, 4]
    assert state["max"] == 5                # all ran at once


def test_return_exceptions_collects_errors_in_order():
    async def ok():
        return 1

    async def boom():
        raise ValueError("kaboom")

    async def run():
        return await bounded_gather(ok(), boom(), ok(), limit=2,
                                    return_exceptions=True)

    res = asyncio.run(run())
    assert res[0] == 1
    assert isinstance(res[1], ValueError)
    assert res[2] == 1


async def _gather(work, *, n, limit):
    return await bounded_gather(*(work(i) for i in range(n)), limit=limit)
