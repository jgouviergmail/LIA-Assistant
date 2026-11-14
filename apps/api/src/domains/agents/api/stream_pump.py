"""Interleave graph chunks and transient cards without losing the actual graph writer."""

import asyncio
from collections.abc import AsyncGenerator

from src.core.constants import STREAM_TEARDOWN_WAIT_SECONDS
from src.core.run_authority import track_graph_writer
from src.infrastructure.async_utils import cancel_and_wait


async def interleave_side_channel[T](
    sse_stream: AsyncGenerator[tuple[T, str]],
    side_queue: asyncio.Queue[T],
    poll_interval: float = 0.3,
) -> AsyncGenerator[tuple[T, str]]:
    """Poll transient cards while a graph's next chunk may wait on a provider.

    Args:
        sse_stream: The graph's chunk and archive-fragment stream.
        side_queue: Cards emitted directly by tools in this invocation.
        poll_interval: Maximum idle delay before checking the side channel.

    Yields:
        The native stream's pairs or a side-channel item with no archive fragment.
    """
    sse_aiter = sse_stream.__aiter__()
    pending: asyncio.Task[tuple[T, str] | None] | None = None

    async def next_chunk() -> tuple[T, str] | None:
        try:
            return await sse_aiter.__anext__()
        except StopAsyncIteration:
            return None

    try:
        while True:
            if pending is None:
                pending = track_graph_writer(asyncio.create_task(next_chunk()))
            done, _ = await asyncio.wait({pending}, timeout=poll_interval)
            while not side_queue.empty():
                try:
                    yield side_queue.get_nowait(), ""
                except asyncio.QueueEmpty:
                    break
            if done:
                result = pending.result()
                pending = None
                if result is None:
                    break
                yield result
    finally:
        if pending is not None and not pending.done():
            await cancel_and_wait(pending, timeout_seconds=STREAM_TEARDOWN_WAIT_SECONDS)
        # A timed-out writer remains held by the run supervisor. Never detach
        # it because this transport has stopped waiting.
    while not side_queue.empty():
        try:
            yield side_queue.get_nowait(), ""
        except asyncio.QueueEmpty:
            break
