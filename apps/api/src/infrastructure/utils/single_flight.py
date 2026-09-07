"""Coalescing concurrent callers onto one execution of the same work.

Two endpoints can serve one screen. When they do, each one asking the sources
the same question at the same moment is not redundancy, it is the same act
performed twice: twice the third-party quota, twice the latency contention,
twice the rows in a register that is supposed to say what was read once.

This module holds the seam that ends it. Whoever asks first runs the work;
whoever asks while it is running waits for that same result. It is deliberately
NOT a cache — a finished run is never handed to a later caller, because the
question "is this still true?" belongs to the caller's own cache, not here.

Design notes, each paid for by a way this can go wrong:

- **The registry is the strong reference.** ``asyncio.create_task`` alone can
  be garbage-collected when the request that started it finishes first — the
  trap ``infrastructure/async_utils`` documents. The entry lives in the
  registry for exactly as long as the task runs.
- **Waiters are shielded.** ``await task`` propagates the awaiter's
  cancellation to the task, so one caller disconnecting would cancel the work
  every other caller is still waiting for.
- **An entry belongs to an event loop.** The registry is module-level and
  outlives any single loop, so a task created on another one must never be
  awaited here: it is a future that could not possibly complete. Such an
  entry is treated as absent, and this is checked BEFORE completion, because
  a foreign task is unusable whether or not it has finished.
- **A failure is shared, then forgotten.** Every waiter sees the same
  exception, and the entry is released, so the next caller retries rather
  than inheriting a poisoned result.

Usage:
    result = await run_single_flight(("cards", user_id), lambda: build())
    if result.joined:
        ...  # another caller was already doing this

The mirror image of ``retry_async`` in this package: both take a FACTORY
rather than an awaitable, because a coroutine can only be awaited once — a
seam holding ``build()`` could neither retry it nor start it on demand. The
factory must return a COROUTINE rather than any awaitable, which is what
``asyncio.create_task`` accepts and therefore what this seam can share.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Hashable
from functools import partial
from typing import Any, NamedTuple, TypeVar

T = TypeVar("T")


class SingleFlightResult[V](NamedTuple):
    """What a coalesced call produced, and whether it produced it.

    Attributes:
        value: The result of the work, shared by every caller of this flight.
        joined: True when another caller was already running it. The caller
            that started the flight sees False — so a counter, a log line or
            a register can tell one act from the callers watching it.
    """

    value: V
    joined: bool


# Heterogeneous by nature: each key holds a task of its own result type, and
# the key is what guarantees a caller gets back what it asked for. The type
# system cannot express that, so the values are ``Any`` here and the narrowing
# happens where the key is known — never through a cast that would claim more
# than is true.
_FLIGHTS: dict[Hashable, asyncio.Task[Any]] = {}


def _current(key: Hashable) -> asyncio.Task[Any] | None:
    """Return the live task for ``key`` on the running loop, if any.

    Args:
        key: The flight identity.

    Returns:
        The task still running for this key on this loop, else None.
    """
    task = _FLIGHTS.get(key)
    if task is None:
        return None
    if task.get_loop() is not asyncio.get_running_loop():
        return None
    return None if task.done() else task


async def run_single_flight(
    key: Hashable,
    factory: Callable[[], Coroutine[Any, Any, T]],
) -> SingleFlightResult[T]:
    """Run ``factory()`` once for every caller that asks while it is running.

    Args:
        key: What makes two calls the same work. Everything that changes the
            result must be part of it — a key that is too coarse hands a
            caller someone else's answer, which is worse than doing the work
            twice.
        factory: Builds the coroutine to run — a coroutine rather than any
            awaitable, because that is what ``asyncio.create_task`` accepts
            and therefore what can be shared. Called only by the caller that
            starts the flight.

    Returns:
        The shared value, and whether this caller joined a running flight.

    Raises:
        Exception: Whatever ``factory()`` raises, to every caller of the
            flight. The entry is released either way.
    """
    task: asyncio.Task[T] | None = _current(key)
    joined = task is not None
    if task is None:
        task = asyncio.create_task(factory())
        _FLIGHTS[key] = task
        task.add_done_callback(partial(_release, key))
    # Shielded: this caller may be cancelled (a client disconnecting) without
    # taking down the work the other callers are waiting for.
    return SingleFlightResult(value=await asyncio.shield(task), joined=joined)


def _release(key: Hashable, done: asyncio.Task[Any]) -> None:
    """Drop the entry, unless a newer flight has already claimed the key.

    Args:
        key: The flight identity.
        done: The task that just finished.
    """
    if _FLIGHTS.get(key) is done:
        del _FLIGHTS[key]


def in_flight_count() -> int:
    """How many flights are registered — for guards and tests, not for callers."""
    return len(_FLIGHTS)


__all__ = ["SingleFlightResult", "in_flight_count", "run_single_flight"]
