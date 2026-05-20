"""SSE keepalive helper.

Wraps an async iterable with a timeout-based keepalive emission so that long
silent phases (eg an LLM call inside a compaction node) do not allow
Cloudflare or any other intermediary to cut the SSE stream as idle.

The existing router-level `last_heartbeat` check (`router.py`) only fires
between two received chunks. When the upstream generator is blocked on an
`await` for tens of seconds, no heartbeat is emitted and intermediaries can
close the connection — exactly what happened during the 2026-05-16
production incident.

Design (revised 2026-05-19 after a ContextVar regression):
- Spawn a SINGLE consumer task that iterates the upstream generator from
  start to finish. All `ContextVar.set()` / `.reset()` performed inside the
  upstream stay within that one task's Context — there is no risk of
  cross-context token resets.
- The wrapper itself reads from a queue. On `queue.get()` timeout it yields
  a `KeepalivePulse` sentinel without disturbing the consumer task.
- On caller-side abort (early break, client disconnect), the consumer task
  is cancelled cleanly in the wrapper's `finally`.

The previous design (a fresh `asyncio.create_task(__anext__())` per
iteration) broke because each `__anext__()` ran in a brand-new Context;
tokens minted by the upstream's `__aenter__` could not be `.reset()` from
the next iteration's Context.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from typing import Any, Final, TypeVar

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class KeepalivePulse:
    """Sentinel emitted by `iter_with_keepalive` when the keepalive timer fires."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return "<KeepalivePulse>"


# Shared singleton — callers compare with `is KEEPALIVE` or `isinstance(_, KeepalivePulse)`.
KEEPALIVE: Final[KeepalivePulse] = KeepalivePulse()

# Internal sentinel pushed into the bridge queue when the upstream finishes.
_DONE_SENTINEL: Final[object] = object()


async def iter_with_keepalive(
    source: AsyncIterable[T],
    keepalive_interval_seconds: float,
) -> AsyncIterator[T | KeepalivePulse]:
    """Yield items from `source`, injecting `KEEPALIVE` sentinels during silences.

    A heartbeat sentinel is yielded after every `keepalive_interval_seconds`
    of silence between consecutive items from the upstream generator. The
    upstream runs inside a single consumer task whose Context is stable, so
    nested `ContextVar.set()/reset()` semantics are preserved end-to-end.

    Args:
        source: The async iterable to consume.
        keepalive_interval_seconds: Max silent gap before yielding a sentinel.
            Must be > 0 to avoid a busy loop.

    Yields:
        Items of type T from the upstream, or `KeepalivePulse` instances.
    """
    if keepalive_interval_seconds <= 0:
        raise ValueError("keepalive_interval_seconds must be > 0")

    queue: asyncio.Queue[Any] = asyncio.Queue()

    async def _consume() -> None:
        try:
            async for item in source:
                await queue.put(item)
        except BaseException as exc:  # noqa: BLE001 - re-raised through the queue
            await queue.put(exc)
            return
        await queue.put(_DONE_SENTINEL)

    consumer: asyncio.Task[None] = asyncio.create_task(_consume())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=keepalive_interval_seconds)
            except TimeoutError:
                # Upstream is still busy. Emit a heartbeat and keep waiting on
                # the SAME consumer task — no item is ever lost.
                yield KEEPALIVE
                continue

            if item is _DONE_SENTINEL:
                return
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        if not consumer.done():
            consumer.cancel()
        try:
            await consumer
        except asyncio.CancelledError:
            # Expected when the wrapper finishes (early break / client
            # disconnect). Suppress so the cancel does not leak past the
            # caller's loop.
            pass
        except StopAsyncIteration:
            # Defensive: an early generator close can surface as StopAsyncIteration
            # — treat it as a clean end-of-stream.
            pass
        except Exception as exc:
            # The consumer already routed its own errors through the queue
            # and yielded them via `raise item`. Anything still raised here
            # is unexpected (failure inside cancel/teardown); log it so a
            # silent failure does not stall the SSE pipeline without trace.
            logger.debug(
                "sse_keepalive_consumer_cleanup_error",
                error=str(exc),
                error_type=type(exc).__name__,
            )
