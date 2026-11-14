"""An operator can retire a stopped graph, never infer its death from a timeout."""

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_execution import ExecutionPhase, ExecutionRevoked, RunAdmission, RunBusy
from src.domains.conversations.execution_models import ConversationExecution
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.infrastructure.streaming import run_admission, run_recovery, runtime_redis
from tests.fixtures.persisted_runtimes import persist_runtime_targets

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(autouse=True)
async def recovery_connections(async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Substitute connection composition alone; keep actual SQL and Redis transitions."""

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    monkeypatch.setattr(run_recovery, "get_db_context", session)


async def _phase(engine: AsyncEngine, admission: RunAdmission) -> ExecutionPhase:
    async with AsyncSession(engine) as db:
        phase = await db.scalar(
            select(ConversationExecution.phase).where(
                ConversationExecution.id == admission.activity_id
            )
        )
        assert phase is not None
        return phase


async def test_quarantine_revokes_writes_but_never_claims_the_worker_stopped(
    reserved: RunAdmission, async_engine: AsyncEngine, redis_client: Redis
) -> None:
    await runtime_redis.open_runtime_writes(redis_client, reserved)
    assert await run_recovery.quarantine(reserved.activity_id, reserved.worker_id) == (
        ExecutionPhase.RECOVERING
    )
    assert await _phase(async_engine, reserved) == ExecutionPhase.RECOVERING
    async with AsyncSession(async_engine) as db:
        with pytest.raises(ExecutionRevoked):
            await ConversationExecutionRepository(db).require_current(reserved)
    with pytest.raises(ExecutionRevoked):
        await runtime_redis.open_runtime_writes(redis_client, reserved)
    busy = await run_admission.reserve_execution(
        reserved.target, run_id=str(uuid4()), stream_id=str(uuid4()), relayed=False
    )
    assert isinstance(busy, RunBusy)


async def test_closure_requires_quarantine_and_the_exact_stopped_worker(
    reserved: RunAdmission, async_engine: AsyncEngine
) -> None:
    with pytest.raises(ValueError):
        await run_recovery.close_stopped(reserved.activity_id, reserved.worker_id)
    await run_recovery.quarantine(reserved.activity_id, reserved.worker_id)
    with pytest.raises(ExecutionRevoked):
        await run_recovery.close_stopped(reserved.activity_id, uuid4())
    assert await _phase(async_engine, reserved) == ExecutionPhase.RECOVERING
    assert await run_recovery.close_stopped(reserved.activity_id, reserved.worker_id) == (
        ExecutionPhase.CLOSED
    )


async def test_recovery_retry_never_closes_the_next_invocation(
    reserved: RunAdmission, async_engine: AsyncEngine
) -> None:
    await run_recovery.quarantine(reserved.activity_id, reserved.worker_id)
    await run_recovery.close_stopped(reserved.activity_id, reserved.worker_id)
    successor = await run_admission.reserve_execution(
        reserved.target, run_id=str(uuid4()), stream_id=str(uuid4()), relayed=False
    )
    assert isinstance(successor, RunAdmission)
    try:
        assert await run_recovery.close_stopped(reserved.activity_id, reserved.worker_id) == (
            ExecutionPhase.CLOSED
        )
        assert await _phase(async_engine, successor) == ExecutionPhase.RUNNING
        async with AsyncSession(async_engine) as db:
            await ConversationExecutionRepository(db).require_current(successor)
    finally:
        await run_admission.release_unstarted_execution(successor)


async def test_a_killed_worker_is_recovered_only_after_its_process_has_joined(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], tmp_path: Path
) -> None:
    (target,) = await persist_runtime_targets(async_engine, committed_user_ids, count=1)
    output = tmp_path / "worker.log"
    with output.open("wb") as destination:
        process = await asyncio.to_thread(
            subprocess.Popen,
            [sys.executable, "-m", "tests.fixtures.execution_crash_worker", str(target.id)],
            env={
                **os.environ,
                "TEST_RECOVERY_DATABASE_URL": async_engine.url.render_as_string(
                    hide_password=False
                ),
            },
            stdout=destination,
            stderr=subprocess.STDOUT,
        )
    try:
        async with asyncio.timeout(60):
            while True:
                lines = (await asyncio.to_thread(output.read_bytes)).splitlines()
                ready = [line for line in lines if line.startswith(b"READY:")]
                if ready:
                    break
                assert process.poll() is None, "The disposable worker exited before admission"
                await asyncio.sleep(0.05)
        line = ready[0]
        _, raw_activity, raw_worker = line.decode().strip().split(":")
        activity, worker = UUID(raw_activity), UUID(raw_worker)
        assert process.returncode is None
        await run_recovery.quarantine(activity, worker)
        async with AsyncSession(async_engine) as db:
            occupied = await ConversationExecutionRepository(db).active_for_owner(target.owner_id)
            assert occupied is not None and occupied.phase == ExecutionPhase.RECOVERING
        process.kill()
        await asyncio.to_thread(process.wait)
        assert process.returncode is not None
        assert await run_recovery.close_stopped(activity, worker) == ExecutionPhase.CLOSED
        async with AsyncSession(async_engine) as db:
            assert (
                await ConversationExecutionRepository(db).active_for_owner(target.owner_id) is None
            )
            assert (
                await db.scalar(
                    select(ConversationExecution.run_id).where(ConversationExecution.id == activity)
                )
                == occupied.run_id
            )
    finally:
        if process.poll() is None:
            process.kill()
        await asyncio.to_thread(process.wait)


@pytest.mark.parametrize("cancel", [False, True])
async def test_redis_failure_or_cancel_leaves_a_retryable_occupied_graph(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    cancel: bool,
) -> None:
    actual_close = runtime_redis.close_runtime_writes

    async def failed_close(*args: object, **kwargs: object) -> bool:
        if cancel:
            raise asyncio.CancelledError
        raise ConnectionError("Redis unavailable")

    monkeypatch.setattr(run_recovery, "close_runtime_writes", failed_close)
    with pytest.raises(asyncio.CancelledError if cancel else ConnectionError):
        await run_recovery.quarantine(reserved.activity_id, reserved.worker_id)
    assert await _phase(async_engine, reserved) == ExecutionPhase.RECOVERING
    with pytest.raises(asyncio.CancelledError if cancel else ConnectionError):
        await run_recovery.close_stopped(reserved.activity_id, reserved.worker_id)
    assert await _phase(async_engine, reserved) == ExecutionPhase.RECOVERING
    monkeypatch.setattr(run_recovery, "close_runtime_writes", actual_close)
    assert await run_recovery.close_stopped(reserved.activity_id, reserved.worker_id) == (
        ExecutionPhase.CLOSED
    )
