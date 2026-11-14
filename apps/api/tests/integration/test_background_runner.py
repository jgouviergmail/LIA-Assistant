"""Detached producers own real SQL admission and deliver through real Redis streams."""

import asyncio
import json
from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.conversation_execution import RunAdmission, RunEnd
from src.domains.agents.api.background_runner import (
    drain_chat_producers,
    get_active_chat_producer_count,
    spawn_chat_run_producer,
)
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.infrastructure.streaming.run_admission import reserve_execution
from src.infrastructure.streaming.run_stream_broker import (
    RunStreamEvent,
    is_cancel_requested,
    request_cancel,
    subscribe,
)
from tests.fixtures.conversation_executions import redis_client as redis_client
from tests.fixtures.conversation_executions import reserved as reserved
from tests.fixtures.persisted_runtimes import persist_runtime_targets

pytestmark = pytest.mark.integration


@pytest.fixture
async def admitted(reserved: RunAdmission, async_engine: AsyncEngine) -> RunAdmission:
    """Reserve a real reconnectable invocation, never forge an ORM or authority token."""
    async with AsyncSession(async_engine) as db:
        await ConversationExecutionRepository(db).close_owned(reserved, end=RunEnd.NORMAL)
        await db.commit()
    admission = await reserve_execution(
        reserved.target,
        run_id=reserved.run_id,
        stream_id=str(uuid4()),
        relayed=True,
        cancellable=True,
    )
    assert isinstance(admission, RunAdmission)
    return admission


async def collect(redis: Redis, stream_id: str) -> list[RunStreamEvent]:
    async with asyncio.timeout(5):
        return [event async for event in subscribe(redis, stream_id) if event.kind != "keepalive"]


def token(content: str) -> ChatStreamChunk:
    return ChatStreamChunk(type="token", content=content, metadata=None)


async def test_producer_publishes_all_chunks_then_closes_authority(
    admitted: RunAdmission,
    redis_client: Redis,
    async_engine: AsyncEngine,
) -> None:
    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        for index in range(5):
            yield token(str(index))

    await spawn_chat_run_producer(chat_stream=stream(), admission=admitted, session_id="session")
    events = await collect(redis_client, admitted.stream_id)
    assert [event.kind for event in events] == ["chunk"] * 5 + ["end"]
    assert events[-1].payload == "completed"
    assert get_active_chat_producer_count() == 0
    async with AsyncSession(async_engine) as db:
        assert (
            await ConversationExecutionRepository(db).active_for_owner(admitted.target.owner_id)
            is None
        )


async def test_failing_generator_publishes_an_explicit_error_and_end(
    admitted: RunAdmission,
    redis_client: Redis,
) -> None:
    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        yield token("partial")
        raise RuntimeError("Test model failed")

    await spawn_chat_run_producer(chat_stream=stream(), admission=admitted, session_id="session")
    events = await collect(redis_client, admitted.stream_id)
    assert [json.loads(event.payload)["type"] for event in events if event.kind == "chunk"] == [
        "token",
        "error",
        "done",
    ]
    assert events[-1].kind == "end" and events[-1].payload == "error"


@pytest.mark.parametrize("source", ["user", "shutdown"])
@pytest.mark.parametrize("replacement", [False, True])
async def test_cancellation_preserves_partial_replacement_and_distinguishes_its_reason(
    admitted: RunAdmission,
    redis_client: Redis,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    replacement: bool,
) -> None:
    monkeypatch.setattr(settings, "background_runs_cancel_poll_seconds", 0.01)
    running = asyncio.Event()
    archived: list[tuple[str, str]] = []

    async def finalize(content: str, reason: str) -> None:
        async with AsyncSession(async_engine) as db:
            assert (
                await ConversationExecutionRepository(db).active_for_owner(admitted.target.owner_id)
                is not None
            )
        archived.append((content, reason))

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        yield token("partial ")
        yield token("answer")
        if replacement:
            yield ChatStreamChunk(
                type="content_replacement", content="enriched answer", metadata=None
            )
        running.set()
        await asyncio.Event().wait()

    producer = spawn_chat_run_producer(
        chat_stream=stream(), admission=admitted, session_id="session", finalize_partial=finalize
    )
    try:
        await asyncio.wait_for(running.wait(), 5)
        if source == "user":
            await request_cancel(redis_client, admitted.stream_id)
        else:
            producer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(producer, 5)
        events = await collect(redis_client, admitted.stream_id)
        reason = "cancelled" if source == "user" else "killed"
        assert events[-1].payload == reason
        assert archived == [("enriched answer" if replacement else "partial answer", reason)]
        done = [
            json.loads(event.payload)
            for event in events
            if event.kind == "chunk" and json.loads(event.payload)["type"] == "done"
        ]
        if source == "user":
            assert len(done) == 1 and done[0]["metadata"]["cancelled"] is True
            assert not await is_cancel_requested(redis_client, admitted.stream_id)
        else:
            assert done == []
        async with AsyncSession(async_engine) as db:
            assert (
                await ConversationExecutionRepository(db).active_for_owner(admitted.target.owner_id)
                is None
            )
    finally:
        if not producer.done():
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)


async def test_hitl_resumption_uses_a_fresh_stream_after_the_previous_end_marker(
    admitted: RunAdmission,
    redis_client: Redis,
) -> None:
    async def phase(content: str) -> AsyncGenerator[ChatStreamChunk]:
        yield token(content)

    await spawn_chat_run_producer(
        chat_stream=phase("question"), admission=admitted, session_id="session"
    )
    resumed = await reserve_execution(
        admitted.target, run_id=admitted.run_id, stream_id=str(uuid4()), relayed=True
    )
    assert isinstance(resumed, RunAdmission)
    await spawn_chat_run_producer(
        chat_stream=phase("answer"), admission=resumed, session_id="session"
    )
    events = await collect(redis_client, resumed.stream_id)
    chunks = [json.loads(event.payload) for event in events if event.kind == "chunk"]
    assert [chunk["content"] for chunk in chunks] == ["answer"]
    assert chunks[0]["metadata"]["run_id"] == admitted.run_id
    assert chunks[0]["metadata"]["stream_id"] == resumed.stream_id != admitted.stream_id
    assert events[-1].payload == "completed"


async def test_supervision_updates_sql_without_any_redis_lease(
    admitted: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "background_runs_heartbeat_seconds", 0.05)
    running, release = asyncio.Event(), asyncio.Event()
    async with AsyncSession(async_engine) as db:
        initial = await ConversationExecutionRepository(db).snapshot_for_owner(
            admitted.target.owner_id
        )
        assert initial is not None

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        yield token("start")
        running.set()
        await release.wait()

    producer = spawn_chat_run_producer(
        chat_stream=stream(), admission=admitted, session_id="session"
    )
    try:
        await asyncio.wait_for(running.wait(), 5)
        async with asyncio.timeout(5):
            while True:
                async with AsyncSession(async_engine) as db:
                    active = await ConversationExecutionRepository(db).snapshot_for_owner(
                        admitted.target.owner_id
                    )
                assert active is not None
                if active.heartbeat_at > initial.heartbeat_at:
                    break
                await asyncio.sleep(0.01)
    finally:
        release.set()
        await producer


async def test_shutdown_drain_reports_unjoined_work_across_accounts(
    admitted: RunAdmission,
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
) -> None:
    (target,) = await persist_runtime_targets(async_engine, committed_user_ids, count=1)
    second = await reserve_execution(
        target, run_id=str(uuid4()), stream_id=str(uuid4()), relayed=True
    )
    assert isinstance(second, RunAdmission)
    fast_started, slow_started, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def stream(
        started: asyncio.Event, finished: asyncio.Event
    ) -> AsyncGenerator[ChatStreamChunk]:
        yield token("started")
        started.set()
        await finished.wait()

    fast = spawn_chat_run_producer(
        chat_stream=stream(fast_started, release), admission=admitted, session_id="fast"
    )
    slow = spawn_chat_run_producer(
        chat_stream=stream(slow_started, asyncio.Event()), admission=second, session_id="slow"
    )
    try:
        await asyncio.wait_for(asyncio.gather(fast_started.wait(), slow_started.wait()), 5)
        drain = asyncio.create_task(drain_chat_producers(timeout=1))
        await asyncio.sleep(0)  # let the drain snapshot the actual two producers
        release.set()
        assert await drain == (1, 1)
    finally:
        release.set()
        slow.cancel()
        await asyncio.gather(fast, slow, return_exceptions=True)
