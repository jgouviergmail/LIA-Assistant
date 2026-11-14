"""Two transports for one owned producer: a bounded local queue or the existing Redis relay."""

import asyncio
from collections.abc import AsyncIterator
from typing import Literal, Protocol

from src.core.constants import CHAT_INLINE_QUEUE_MAX_CHUNKS
from src.domains.agents.api.schemas import ChatStreamChunk
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.streaming.run_stream_broker import publish_chunk, publish_end

type RunEndStatus = Literal["completed", "error", "killed", "cancelled"]


class RunOutput(Protocol):
    """Transport owns no execution authority and cannot transfer a graph admission."""

    async def publish(self, chunk: ChatStreamChunk) -> None:
        """Publish one ordered chunk, applying the transport's backpressure."""
        ...

    async def finish(self, status: RunEndStatus) -> None:
        """End this invocation's transport, without claiming its graph has joined."""
        ...


class RedisRunOutput:
    """A disconnected subscriber does not stop this durable transport's producer."""

    def __init__(self, stream_id: str) -> None:
        self.stream_id = stream_id

    async def publish(self, chunk: ChatStreamChunk) -> None:
        await publish_chunk(await get_redis_cache(), self.stream_id, chunk.model_dump_json())

    async def finish(self, status: RunEndStatus) -> None:
        await publish_end(await get_redis_cache(), self.stream_id, status)


class InlineRunOutput:
    """A request-local queue; abandonment unblocks a full queue before cancellation."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[ChatStreamChunk | None] = asyncio.Queue(
            maxsize=CHAT_INLINE_QUEUE_MAX_CHUNKS,
        )
        self._abandoned = False

    async def publish(self, chunk: ChatStreamChunk) -> None:
        if not self._abandoned:
            await self._queue.put(chunk)

    async def finish(self, status: RunEndStatus) -> None:
        if not self._abandoned:
            await self._queue.put(None)

    async def chunks(self) -> AsyncIterator[ChatStreamChunk]:
        """The HTTP reader owns its queue, never the generator's internal contexts."""
        while (chunk := await self.read()) is not None:
            yield chunk

    async def read(self, timeout: float | None = None) -> ChatStreamChunk | None:
        """Await only the queue; a heartbeat timeout never cancels the producer."""
        return await asyncio.wait_for(self._queue.get(), timeout)

    def abandon(self) -> None:
        """No departed reader can hold a producer in an unbounded publish wait."""
        self._abandoned = True
        while not self._queue.empty():
            self._queue.get_nowait()
        self._queue.put_nowait(None)
