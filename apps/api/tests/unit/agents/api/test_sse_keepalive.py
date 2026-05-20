"""Unit tests for `iter_with_keepalive`.

Validates the heartbeat injection logic that protects long SSE streams from
intermediary idle cuts (Cloudflare, etc).

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


async def _emit(values: list[tuple[float, T]]) -> AsyncIterator[T]:
    """Async iterator that sleeps `delay` then yields each `value`."""
    for delay, value in values:
        if delay > 0:
            await asyncio.sleep(delay)
        yield value


async def test_yields_items_when_source_is_fast() -> None:
    """No heartbeat fires when items arrive faster than the interval."""
    source = _emit([(0.0, "a"), (0.0, "b"), (0.0, "c")])
    collected: list[object] = []
    async for item in iter_with_keepalive(source, keepalive_interval_seconds=0.5):
        collected.append(item)
    assert collected == ["a", "b", "c"]


async def test_emits_heartbeat_during_silence() -> None:
    """When a gap exceeds the interval, KEEPALIVE pulses are interleaved."""
    # 0.25s gap with a 0.05s interval → at least 4 heartbeats before the item.
    source = _emit([(0.25, "delayed")])
    collected: list[object] = []
    async for item in iter_with_keepalive(source, keepalive_interval_seconds=0.05):
        collected.append(item)

    real_items = [x for x in collected if not isinstance(x, KeepalivePulse)]
    pulses = [x for x in collected if isinstance(x, KeepalivePulse)]
    assert real_items == ["delayed"]
    assert len(pulses) >= 3


async def test_pending_task_is_preserved_across_heartbeats() -> None:
    """The chunk that was being awaited when the timer fired must not be lost."""
    # One item with a long delay; we expect multiple heartbeats then the item.
    source = _emit([(0.15, "kept"), (0.0, "next")])
    collected: list[object] = []
    async for item in iter_with_keepalive(source, keepalive_interval_seconds=0.03):
        collected.append(item)

    # 'kept' must appear (proof the awaited task wasn't cancelled by heartbeats)
    # and 'next' must follow it immediately after.
    real = [x for x in collected if not isinstance(x, KeepalivePulse)]
    assert real == ["kept", "next"]


async def test_pulses_use_shared_sentinel() -> None:
    """All emitted heartbeats are the same singleton instance."""
    source = _emit([(0.15, "x")])
    pulses: list[object] = []
    async for item in iter_with_keepalive(source, keepalive_interval_seconds=0.03):
        if isinstance(item, KeepalivePulse):
            pulses.append(item)
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

    async def slow_then_signal() -> AsyncIterator[str]:
        try:
            await asyncio.sleep(10)
            yield "should not arrive"
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async for item in iter_with_keepalive(slow_then_signal(), keepalive_interval_seconds=0.02):
        # Break on the first heartbeat — simulates a client disconnect.
        if isinstance(item, KeepalivePulse):
            break

    await asyncio.wait_for(cancelled.wait(), timeout=1.0)


async def test_contextvar_set_and_reset_survives_keepalives() -> None:
    """Regression guard for the 2026-05-19 incident.

    The previous design spawned a fresh `asyncio.create_task(__anext__())` on
    every iteration; each one ran in its own Context, so a `ContextVar.set()`
    performed inside the upstream generator could not be `.reset()` on exit
    (the token belonged to a different Context). The current design routes
    all upstream work through a single consumer task with a stable Context.

    This test sets a ContextVar inside an upstream generator that yields
    twice with a gap that forces at least one heartbeat in between, then
    resets the token on exit. With the broken design this would raise
    `ValueError: <Token ...> was created in a different Context`.
    """
    import contextvars

    var: contextvars.ContextVar[str | None] = contextvars.ContextVar("ka_test_var", default=None)

    async def upstream() -> AsyncIterator[str]:
        token = var.set("inside")
        try:
            yield "first"
            await asyncio.sleep(0.15)  # forces several heartbeats
            yield "second"
        finally:
            var.reset(token)  # MUST work despite intervening heartbeats

    items: list[object] = []
    async for it in iter_with_keepalive(upstream(), keepalive_interval_seconds=0.03):
        items.append(it)

    real = [x for x in items if not isinstance(x, KeepalivePulse)]
    pulses = [x for x in items if isinstance(x, KeepalivePulse)]
    assert real == ["first", "second"]
    assert len(pulses) >= 2
    assert var.get() is None  # token reset succeeded cleanly
