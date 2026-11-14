"""The real transport producer owns SQL authority through finalization and early cancellation."""

import asyncio
from collections.abc import AsyncGenerator

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.constants import CHAT_INLINE_QUEUE_MAX_CHUNKS
from src.core.conversation_execution import ExecutionPhase, RunAdmission, RunEnd
from src.core.run_authority import current_run_authority
from src.domains.agents.api import background_runner
from src.domains.agents.api.background_runner import spawn_chat_run_producer
from src.domains.agents.api.chat_response import inline_sse
from src.domains.agents.api.run_output import InlineRunOutput, RunEndStatus
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.conversations.execution_models import ConversationExecution

pytestmark = pytest.mark.integration


async def test_a_slow_http_subscriber_cannot_create_an_unbounded_second_buffer(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
) -> None:
    all_generated = asyncio.Event()
    produced: list[int] = []

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        for index in range(CHAT_INLINE_QUEUE_MAX_CHUNKS * 3):
            produced.append(index)
            yield ChatStreamChunk(type="token", content=str(index), metadata=None)
        all_generated.set()

    output = InlineRunOutput()
    task = spawn_chat_run_producer(
        chat_stream=stream(), admission=reserved, session_id="session", output=output
    )
    subscriber = inline_sse(output, task, None)
    try:
        assert await anext(subscriber) == "retry: 5000\n\n"
        assert '"type":"token"' in await anext(subscriber)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(all_generated.wait(), 0.1)
        # One delivered chunk, the bounded queue, and one pending publish.
        assert len(produced) <= CHAT_INLINE_QUEUE_MAX_CHUNKS + 2
        assert not task.done()
    finally:
        await subscriber.aclose()
    assert task.done() and await closed(async_engine, reserved)


async def closed(engine: AsyncEngine, admission: RunAdmission) -> bool:
    async with AsyncSession(engine) as db:
        phase = await db.scalar(
            select(ConversationExecution.phase).where(
                ConversationExecution.id == admission.activity_id,
            )
        )
        return phase == ExecutionPhase.CLOSED


async def test_the_producer_not_its_subscriber_owns_the_admission(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    redis_client: Redis,
) -> None:
    observed: list[bool] = []

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        authority = current_run_authority()
        observed.append(authority is not None and authority.admission == reserved)
        yield ChatStreamChunk(type="token", content="hello", metadata=None)

    task = spawn_chat_run_producer(
        chat_stream=stream(),
        admission=reserved,
        session_id="session",
    )
    await task
    assert observed == [True]
    assert await closed(async_engine, reserved)


async def test_cancellation_before_the_producers_first_instruction_releases_unused_admission(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
) -> None:
    executed = False

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        nonlocal executed
        executed = True
        yield ChatStreamChunk(type="token", content="unreachable", metadata=None)

    task = spawn_chat_run_producer(
        chat_stream=stream(),
        admission=reserved,
        session_id="session",
    )
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not executed
    async with asyncio.timeout(5):
        while not await closed(async_engine, reserved):
            await asyncio.sleep(0.01)


class BrokenOutput:
    """An actually failing transport, not a no-op substitute for finalization."""

    async def publish(self, chunk: ChatStreamChunk) -> None:
        raise ConnectionError("Test transport unavailable")

    async def finish(self, status: RunEndStatus) -> None:
        raise ConnectionError("Test transport unavailable")


async def test_transport_failure_still_archives_observed_output_before_releasing_authority(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
) -> None:
    archived: list[tuple[str, str]] = []

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        yield ChatStreamChunk(type="token", content="observed partial", metadata=None)

    async def archive(content: str, reason: str) -> None:
        assert not await closed(async_engine, reserved)
        archived.append((content, reason))

    await spawn_chat_run_producer(
        chat_stream=stream(),
        admission=reserved,
        session_id="session",
        output=BrokenOutput(),
        finalize_partial=archive,
    )
    assert archived == [("observed partial", "error")]
    assert await closed(async_engine, reserved)


async def test_repeated_cancel_cannot_detach_the_partial_archive(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
) -> None:
    running, filing, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    archived: list[str] = []

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        yield ChatStreamChunk(type="token", content="partial", metadata=None)
        running.set()
        await asyncio.Event().wait()

    async def archive(content: str, reason: str) -> None:
        filing.set()
        await release.wait()
        archived.append(content)

    task = spawn_chat_run_producer(
        chat_stream=stream(),
        admission=reserved,
        session_id="session",
        finalize_partial=archive,
    )
    try:
        await running.wait()
        task.cancel()
        await filing.wait()
        task.cancel()
        assert not await closed(async_engine, reserved)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert archived == ["partial"] and await closed(async_engine, reserved)
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_unconsumed_inline_response_is_owned_until_its_request_ends(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
) -> None:
    body_started = asyncio.Event()
    output = InlineRunOutput()
    producer: asyncio.Task[None] | None = None

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        body_started.set()
        while True:
            yield ChatStreamChunk(type="token", content="bounded", metadata=None)

    async def request() -> None:
        nonlocal producer
        producer = spawn_chat_run_producer(
            chat_stream=stream(),
            admission=reserved,
            session_id="session",
            output=output,
        )
        background_runner.link_inline_request_lifetime(producer, output)
        await body_started.wait()
        # No iterator was consumed; ending the request still cancels its graph.

    try:
        await asyncio.create_task(request())
        assert producer is not None
        await asyncio.gather(producer, return_exceptions=True)
        assert await closed(async_engine, reserved)
    finally:
        if producer is not None:
            await background_runner.stop_inline_producer(producer, output)


async def test_refused_startup_says_failure_to_the_inline_reader(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
) -> None:
    from src.domains.conversations.execution_repository import ConversationExecutionRepository

    async with AsyncSession(async_engine) as db:
        await ConversationExecutionRepository(db).close_owned(reserved, end=RunEnd.NORMAL)
        await db.commit()

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        pytest.fail("A refused producer started its model")
        yield ChatStreamChunk(type="done", content="", metadata=None)

    output = InlineRunOutput()
    task = spawn_chat_run_producer(
        chat_stream=stream(),
        admission=reserved,
        session_id="session",
        output=output,
    )
    chunks = [chunk async for chunk in output.chunks()]
    await asyncio.gather(task, return_exceptions=True)
    assert [chunk.type for chunk in chunks] == ["error", "done"]


async def test_failed_done_publication_is_not_read_as_a_delivered_terminal_chunk(
    reserved: RunAdmission,
) -> None:
    class RecoveringOutput:
        def __init__(self) -> None:
            self.refused = False
            self.delivered: list[str] = []

        async def publish(self, chunk: ChatStreamChunk) -> None:
            if chunk.type == "done" and not self.refused:
                self.refused = True
                raise ConnectionError("Test lost done")
            self.delivered.append(chunk.type)

        async def finish(self, status: RunEndStatus) -> None:
            assert status == "error"

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        yield ChatStreamChunk(type="done", content="", metadata=None)

    output = RecoveringOutput()
    await spawn_chat_run_producer(
        chat_stream=stream(),
        admission=reserved,
        session_id="session",
        output=output,
    )
    assert output.delivered == ["error", "done"]
