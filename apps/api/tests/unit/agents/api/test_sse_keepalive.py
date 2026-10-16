"""Unit tests for `iter_with_keepalive`.

Validates the heartbeat injection logic that protects long SSE streams from
intermediary idle cuts (Cloudflare, etc).

Every silence here is SEQUENCED, never timed: the upstream stays silent until
the consumer has seen as many heartbeats as the property needs, then it is
released. Timed with sleeps (« a 0.25 s gap and a 0.05 s interval give at least
three pulses »), a starved event loop woke the gap and the timers in the same
iteration and the count fell short (measured 2026-10-15 under load: two pulses);
sequenced, a slow loop only makes the same pulses arrive later. The clock is
left to the one property that is about it: no pulse while items arrive faster
than the interval.

Phase: F4.5 — Compaction v2 / Task 2.3
Created: 2026-05-19
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TypeVar

import pytest

from src.domains.agents.api.sse_keepalive import (
    KEEPALIVE,
    KeepalivePulse,
    iter_with_keepalive,
)

T = TypeVar("T")

#: A short interval: the tests wait on pulses, never on a duration.
PULSE_SECONDS = 0.01

#: Bounds a broken wrapper that never pulses — a hang guard, never an oracle.
HANG_GUARD_SECONDS = 10


async def _emit(values: list[tuple[float, T]]) -> AsyncIterator[T]:
    """Async iterator that sleeps `delay` then yields each `value`."""
    for delay, value in values:
        if delay > 0:
            await asyncio.sleep(delay)
        yield value


async def _gated(release: asyncio.Event, *values: str) -> AsyncIterator[str]:
    """An upstream silent until `release` is set, then yielding `values`."""
    await release.wait()
    for value in values:
        yield value


async def _collect(
    source: AsyncIterator[str], *, release: asyncio.Event, after_pulses: int
) -> list[object]:
    """Drain the wrapper, releasing the upstream once `after_pulses` heartbeats came."""
    collected: list[object] = []
    pulses = 0
    async with asyncio.timeout(HANG_GUARD_SECONDS):
        async for item in iter_with_keepalive(source, keepalive_interval_seconds=PULSE_SECONDS):
            collected.append(item)
            if isinstance(item, KeepalivePulse):
                pulses += 1
                if pulses == after_pulses:
                    release.set()
    return collected


def _pulses_before(collected: list[object], value: str) -> int:
    """How many heartbeats reached the caller before `value` did."""
    return sum(isinstance(item, KeepalivePulse) for item in collected[: collected.index(value)])


async def test_yields_items_when_source_is_fast() -> None:
    """No heartbeat fires when items arrive faster than the interval.

    The interval is far beyond any stall a loaded host imposes on items that
    are already there: the property holds by construction, not by luck.
    """
    source = _emit([(0.0, "a"), (0.0, "b"), (0.0, "c")])
    collected: list[object] = []
    async for item in iter_with_keepalive(source, keepalive_interval_seconds=60):
        collected.append(item)
    assert collected == ["a", "b", "c"]


async def test_emits_heartbeat_during_silence() -> None:
    """While the upstream is silent, KEEPALIVE pulses keep reaching the caller."""
    release = asyncio.Event()

    collected = await _collect(_gated(release, "delayed"), release=release, after_pulses=3)

    assert [x for x in collected if not isinstance(x, KeepalivePulse)] == ["delayed"]
    assert _pulses_before(collected, "delayed") >= 3


async def test_pending_task_is_preserved_across_heartbeats() -> None:
    """The chunk that was being awaited when the timer fired must not be lost."""
    release = asyncio.Event()

    collected = await _collect(_gated(release, "kept", "next"), release=release, after_pulses=2)

    # 'kept' arrives after heartbeats (proof the awaited consumer survived them)
    # and 'next' follows it.
    assert [x for x in collected if not isinstance(x, KeepalivePulse)] == ["kept", "next"]
    assert _pulses_before(collected, "kept") >= 2


async def test_pulses_use_shared_sentinel() -> None:
    """All emitted heartbeats are the same singleton instance."""
    release = asyncio.Event()

    collected = await _collect(_gated(release, "x"), release=release, after_pulses=3)

    pulses = [x for x in collected if isinstance(x, KeepalivePulse)]
    assert len(pulses) >= 3
    assert all(p is KEEPALIVE for p in pulses)


async def test_terminates_when_source_exhausts() -> None:
    """The wrapper exits cleanly on StopAsyncIteration from the source."""

    async def empty() -> AsyncIterator[str]:
        if False:  # pragma: no cover
            yield "never"

    collected: list[object] = []
    async for item in iter_with_keepalive(empty(), keepalive_interval_seconds=0.1):
        collected.append(item)
    assert collected == []


async def test_invalid_interval_raises() -> None:
    """A zero or negative interval is rejected at first use."""
    source = _emit([(0.0, "x")])
    with pytest.raises(ValueError):
        async for _ in iter_with_keepalive(source, keepalive_interval_seconds=0):
            pass


async def test_propagates_source_exception() -> None:
    """Errors raised by the source bubble up to the caller."""

    async def failing() -> AsyncIterator[str]:
        yield "ok"
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        async for _ in iter_with_keepalive(failing(), keepalive_interval_seconds=0.1):
            pass


async def test_cancels_pending_task_on_caller_stop() -> None:
    """Breaking out of the loop early cancels the pending __anext__ task."""

    cancelled = asyncio.Event()

    async def silent_then_signal() -> AsyncIterator[str]:
        try:
            await asyncio.Event().wait()  # never set: only a cancellation ends it
            yield "should not arrive"
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async with asyncio.timeout(HANG_GUARD_SECONDS):
        async for item in iter_with_keepalive(
            silent_then_signal(), keepalive_interval_seconds=PULSE_SECONDS
        ):
            # Break on the first heartbeat — simulates a client disconnect.
            if isinstance(item, KeepalivePulse):
                break
        await cancelled.wait()


async def test_contextvar_set_and_reset_survives_keepalives() -> None:
    """Regression guard for the 2026-05-19 incident.

    The previous design spawned a fresh `asyncio.create_task(__anext__())` on
    every iteration; each one ran in its own Context, so a `ContextVar.set()`
    performed inside the upstream generator could not be `.reset()` on exit
    (the token belonged to a different Context). The current design routes
    all upstream work through a single consumer task with a stable Context.

    This test sets a ContextVar inside an upstream generator that yields
    twice with heartbeats forced in between (the upstream waits for them),
    then resets the token on exit. With the broken design this would raise
    `ValueError: <Token ...> was created in a different Context`.
    """
    import contextvars

    var: contextvars.ContextVar[str | None] = contextvars.ContextVar("ka_test_var", default=None)
    release = asyncio.Event()

    async def upstream() -> AsyncIterator[str]:
        token = var.set("inside")
        try:
            yield "first"
            await release.wait()  # silent until heartbeats came through
            yield "second"
        finally:
            var.reset(token)  # MUST work despite intervening heartbeats

    items = await _collect(upstream(), release=release, after_pulses=2)

    real = [x for x in items if not isinstance(x, KeepalivePulse)]
    assert real == ["first", "second"]
    assert _pulses_before(items, "second") - _pulses_before(items, "first") >= 2
    assert var.get() is None  # token reset succeeded cleanly
