"""A transport end never releases a graph whose actual writer is still alive."""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.constants import REDIS_KEY_HITL_PENDING_PREFIX
from src.core.conversation_execution import (
    ExecutionPhase,
    ExecutionRevoked,
    RunAdmission,
    RunBusy,
    RunEnd,
)
from src.core.run_authority import current_run_authority, track_graph_writer
from src.domains.agents.api.service import AgentService
from src.domains.conversations.execution_models import ConversationExecution
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.infrastructure.streaming import run_admission, runtime_redis
from tests.fixtures.persisted_runtimes import persist_runtime_targets

pytestmark = pytest.mark.integration


async def phase_of(engine: AsyncEngine, admission: RunAdmission) -> ExecutionPhase:
    async with AsyncSession(engine) as db:
        phase = await db.scalar(
            select(ConversationExecution.phase).where(
                ConversationExecution.id == admission.activity_id,
            )
        )
        assert phase is not None
        return phase


async def test_a_suspended_and_joined_invocation_releases_its_slot(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
) -> None:
    async with run_admission.owned_execution(reserved) as authority:
        assert current_run_authority() is authority
        assert authority.admission == reserved
        assert await phase_of(async_engine, reserved) == ExecutionPhase.RUNNING
    assert current_run_authority() is None
    assert await phase_of(async_engine, reserved) == ExecutionPhase.CLOSED


async def test_unknown_stop_stays_occupied_until_the_actual_writer_is_joined(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_admission, "STREAM_TEARDOWN_WAIT_SECONDS", 0.01)
    started, release = asyncio.Event(), asyncio.Event()
    observed_revocation: list[bool] = []

    async def stubborn_writer() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()
            authority = current_run_authority()
            assert authority is not None
            observed_revocation.append(authority.revoked)

    writer: asyncio.Task[None] | None = None
    try:
        async with run_admission.owned_execution(reserved):
            writer = track_graph_writer(asyncio.create_task(stubborn_writer()))
            await started.wait()
        assert await phase_of(async_engine, reserved) == ExecutionPhase.RECOVERING
        busy = await run_admission.reserve_execution(
            reserved.target,
            run_id=str(uuid4()),
            stream_id=str(uuid4()),
            relayed=True,
        )
        assert isinstance(busy, RunBusy) and busy.phase == ExecutionPhase.RECOVERING
        release.set()
        await writer
        async with asyncio.timeout(5):
            while await phase_of(async_engine, reserved) != ExecutionPhase.CLOSED:
                await asyncio.sleep(0.01)
        assert observed_revocation == [True]
    finally:
        release.set()
        if writer is not None:
            await asyncio.gather(writer, return_exceptions=True)


async def test_a_nested_owner_cannot_close_the_outer_invocation(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
) -> None:
    async with run_admission.owned_execution(reserved) as outer:
        async with run_admission.owned_execution(reserved) as inner:
            assert inner is outer
        assert await phase_of(async_engine, reserved) == ExecutionPhase.RUNNING
        assert not outer.revoked
    assert await phase_of(async_engine, reserved) == ExecutionPhase.CLOSED


async def test_closed_authority_cannot_start_another_producer(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
) -> None:
    async with AsyncSession(async_engine) as db:
        assert await ConversationExecutionRepository(db).close_owned(reserved, end=RunEnd.NORMAL)
        await db.commit()
    with pytest.raises(ExecutionRevoked):
        async with run_admission.owned_execution(reserved):
            pytest.fail("A closed authority reached the producer body")


async def test_cancellation_after_commit_cannot_abandon_an_unstarted_admission(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    committed, release = asyncio.Event(), asyncio.Event()
    first = True

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        nonlocal first
        pause = first
        first = False
        async with AsyncSession(async_engine) as db:
            yield db
            await db.commit()
            if pause:
                committed.set()
                await release.wait()

    monkeypatch.setattr(run_admission, "get_db_context", session)
    (target,) = await persist_runtime_targets(async_engine, committed_user_ids, count=1)
    request = asyncio.create_task(
        run_admission.reserve_execution(
            target,
            run_id=str(uuid4()),
            stream_id=str(uuid4()),
            relayed=False,
        )
    )
    try:
        await committed.wait()
        request.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await request
        async with AsyncSession(async_engine) as db:
            assert (
                await ConversationExecutionRepository(db).active_for_owner(target.owner_id) is None
            )
    finally:
        release.set()
        await asyncio.gather(request, return_exceptions=True)


async def test_the_actual_stream_pump_stays_owned_after_its_bounded_stop(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_admission, "STREAM_TEARDOWN_WAIT_SECONDS", 0.01)
    monkeypatch.setattr("src.domains.agents.api.stream_pump.STREAM_TEARDOWN_WAIT_SECONDS", 0.01)
    started, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def stream() -> AsyncGenerator[tuple[str, str]]:
        try:
            started.set()
            await asyncio.Event().wait()
            yield "unreachable", ""
        finally:
            await release.wait()
            finished.set()

    async def consume() -> None:
        async for _ in AgentService._interleave_side_channel(stream(), asyncio.Queue()):
            pass

    consumer: asyncio.Task[None] | None = None
    try:
        async with run_admission.owned_execution(reserved):
            consumer = asyncio.create_task(consume())
            await started.wait()
            consumer.cancel()
            with pytest.raises(asyncio.CancelledError):
                await consumer
        assert not finished.is_set()
        assert await phase_of(async_engine, reserved) == ExecutionPhase.RECOVERING
        release.set()
        async with asyncio.timeout(5):
            await finished.wait()
            while await phase_of(async_engine, reserved) != ExecutionPhase.CLOSED:
                await asyncio.sleep(0.01)
    finally:
        release.set()
        if consumer is not None:
            await asyncio.gather(consumer, return_exceptions=True)


async def test_owner_opens_and_closes_actual_runtime_redis_writes(
    reserved: RunAdmission,
    redis_client: Redis,
) -> None:
    async with run_admission.owned_execution(reserved):
        await runtime_redis.write_runtime_string(
            redis_client,
            reserved.target.runtime_id,
            key=f"{REDIS_KEY_HITL_PENDING_PREFIX}{reserved.target.runtime_id}",
            value="question",
            ttl_seconds=30,
        )
    assert (
        await redis_client.hget(
            runtime_redis.runtime_writer_key(reserved.target),
            "phase",
        )
        == "closed"
    )


async def test_cancellation_during_initial_validation_releases_unused_authority(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    first = True

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        nonlocal first
        async with AsyncSession(async_engine) as db:
            if first:
                first = False
                started.set()
                await asyncio.Event().wait()
            yield db
            await db.commit()

    monkeypatch.setattr(run_admission, "get_db_context", session)
    monkeypatch.setattr(runtime_redis, "get_db_context", session)

    async def enter() -> None:
        async with run_admission.owned_execution(reserved):
            pytest.fail("The producer started after its requester cancelled")

    entering = asyncio.create_task(enter())
    try:
        await started.wait()
        entering.cancel()
        with pytest.raises(asyncio.CancelledError):
            await entering
        assert await phase_of(async_engine, reserved) == ExecutionPhase.CLOSED
    finally:
        entering.cancel()
        await asyncio.gather(entering, return_exceptions=True)


async def test_redis_failure_keeps_admission_until_explicit_revocation_succeeds(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restored = False
    close = runtime_redis.close_runtime_writes

    async def interrupted_close(
        redis: runtime_redis.RuntimeRedisClient,
        admission: RunAdmission,
    ) -> bool:
        if not restored:
            raise ConnectionError("Test Redis unavailable")
        return await close(redis, admission)

    monkeypatch.setattr(run_admission, "close_runtime_writes", interrupted_close)
    monkeypatch.setattr(settings, "background_runs_heartbeat_seconds", 0.01)
    try:
        async with run_admission.owned_execution(reserved):
            pass
        assert await phase_of(async_engine, reserved) == ExecutionPhase.RECOVERING
        busy = await run_admission.reserve_execution(
            reserved.target,
            run_id=str(uuid4()),
            stream_id=str(uuid4()),
            relayed=False,
        )
        assert isinstance(busy, RunBusy)
    finally:
        restored = True
        async with asyncio.timeout(5):
            while await phase_of(async_engine, reserved) != ExecutionPhase.CLOSED:
                await asyncio.sleep(0.01)


async def test_failed_heartbeat_revokes_before_cancelling_the_producer(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    open_writes = runtime_redis.open_runtime_writes
    calls = 0

    async def lost_renewal(
        redis: runtime_redis.RuntimeRedisClient,
        admission: RunAdmission,
    ) -> None:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise ConnectionError("Test renewal lost")
        await open_writes(redis, admission)

    monkeypatch.setattr(run_admission, "open_runtime_writes", lost_renewal)
    monkeypatch.setattr(settings, "background_runs_heartbeat_seconds", 0.01)
    with pytest.raises(ExecutionRevoked):
        async with run_admission.owned_execution(reserved) as authority:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                assert authority.revoked
                raise
    assert calls == 2
    assert await phase_of(async_engine, reserved) == ExecutionPhase.CLOSED
