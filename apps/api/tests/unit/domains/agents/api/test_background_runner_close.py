"""A stopped run closes its chat stream in its own task, wherever the stop lands.

The producer is cancelled by the person's stop (or the shutdown drain) at whatever
point it is suspended. Inside the generator chain the cancellation unwinds it in
place; while the producer awaits its own Redis publication, the generators sit at a
``yield`` nobody resumes — and were left to the event loop's finalizer, which closes
them later in ANOTHER task: the turn's exits then ran in a context that is not theirs
(every ``ContextVar`` reset refused, the journey closed as an error, the run's
clients never released).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest

from src.domains.agents.api import background_runner
from src.domains.agents.api.schemas import ChatStreamChunk

pytestmark = pytest.mark.unit


async def test_a_run_stopped_while_publishing_closes_its_stream_in_its_own_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publishing = asyncio.Event()
    closed_in: list[asyncio.Task[object] | None] = []

    async def publish_forever(*_args: object) -> None:
        publishing.set()
        await asyncio.sleep(3600)  # the stop lands here, outside the generator

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        try:
            yield ChatStreamChunk(type="token", content="hello", metadata=None)
            yield ChatStreamChunk(type="token", content=" never", metadata=None)
        finally:
            closed_in.append(asyncio.current_task())

    monkeypatch.setattr(background_runner, "get_redis_cache", AsyncMock(return_value=object()))
    monkeypatch.setattr(background_runner, "publish_chunk", publish_forever)
    monkeypatch.setattr(background_runner, "is_cancel_requested", AsyncMock(return_value=False))
    monkeypatch.setattr(background_runner, "_finalize_abnormal", AsyncMock())

    producer = asyncio.create_task(
        background_runner._produce(stream(), "run", "run", "user", "session", None)
    )
    await asyncio.wait_for(publishing.wait(), timeout=5)
    producer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await producer

    assert closed_in == [producer]
