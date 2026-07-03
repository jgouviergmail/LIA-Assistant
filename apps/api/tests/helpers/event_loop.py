"""Event-loop responsiveness helpers for async-path regression tests.

Used to prove that a code path does not block the running event loop
(audit rule: no synchronous network or CPU-heavy call on an async path).
The measurement runs a high-frequency ticker coroutine concurrently with
the code under test and records the largest scheduling gap observed.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

# Ticker period. Kept small so a blocked loop is detected quickly, but
# large enough to be reliable under Windows timer granularity (~15 ms).
_TICK_SECONDS = 0.005


async def measure_max_loop_stall(
    coro_factory: Callable[[], Awaitable[T]],
) -> tuple[float, T]:
    """Run a coroutine while measuring the worst event-loop stall.

    A ticker task sleeps in small increments; if the loop is blocked by a
    synchronous call inside ``coro_factory``, the ticker wakes up late and
    the gap is recorded.

    Args:
        coro_factory: Zero-arg callable returning the awaitable under test.

    Returns:
        Tuple of (max observed stall in seconds beyond the expected tick,
        result of the awaited coroutine).
    """
    stalls: list[float] = []
    done = asyncio.Event()

    async def _ticker() -> None:
        loop = asyncio.get_running_loop()
        last = loop.time()
        while not done.is_set():
            await asyncio.sleep(_TICK_SECONDS)
            now = loop.time()
            stalls.append(now - last - _TICK_SECONDS)
            last = now

    ticker = asyncio.create_task(_ticker())
    # Let the ticker take its first samples before starting the workload.
    await asyncio.sleep(_TICK_SECONDS * 4)
    try:
        result = await coro_factory()
    finally:
        done.set()
        await ticker

    return (max(stalls) if stalls else 0.0, result)
