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


async def assert_workload_off_loop(
    coro_factory: Callable[[], Awaitable[T]],
    blocking_baseline: Callable[[], object],
    absolute_threshold_seconds: float,
    context: str,
) -> T:
    """Assert a workload does not stall the loop, robust to machine load.

    Fast path: if the measured stall stays under the absolute threshold,
    the workload passes with a single measurement (quiet machines, the
    common case). Under heavy machine load (pytest-xdist saturating every
    core, CI contention) the ticker coroutine itself gets starved by the
    OS scheduler and can exceed any absolute threshold spuriously — the
    stall then measures the machine, not the event loop. In that case a
    calibration pass measures the stall of running ``blocking_baseline``
    synchronously ON the loop in the same environment, and the workload
    stall must stay under half of it: scheduler noise inflates both
    measurements alike, while a regression to a synchronous implementation
    stalls as long as the baseline itself and still fails.

    Args:
        coro_factory: Zero-arg callable returning the awaitable under test.
        blocking_baseline: Zero-arg synchronous callable reproducing the
            blocking behavior a regressed implementation would have
            (e.g. the sync variant of the code under test).
        absolute_threshold_seconds: Stall accepted without calibration.
        context: Short label for the assertion message.

    Returns:
        The result of the awaited coroutine.
    """
    max_stall, result = await measure_max_loop_stall(coro_factory)
    if max_stall < absolute_threshold_seconds:
        return result

    async def _blocking_on_loop() -> object:
        return blocking_baseline()

    baseline_stall, _ = await measure_max_loop_stall(_blocking_on_loop)
    assert max_stall < baseline_stall * 0.5, (
        f"event loop stalled {max_stall * 1000:.0f} ms during {context} "
        f"(absolute threshold {absolute_threshold_seconds * 1000:.0f} ms, "
        f"blocking baseline {baseline_stall * 1000:.0f} ms)"
    )
    return result
