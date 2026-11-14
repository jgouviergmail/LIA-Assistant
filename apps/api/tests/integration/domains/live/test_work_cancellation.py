"""Cancellation during a committed admission joins and compensates the exact unused work."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_execution import (
    ExecutionKind,
    ExecutionPhase,
    RunAdmission,
)
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.reservation_repository import ConversationReservationRepository
from src.infrastructure.streaming.reservation_work import commit_work, fork_relay
from tests.fixtures.learning_sources import Sources
from tests.fixtures.learning_sources import sources as sources

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("closing", [False, True])
async def test_cancelled_commit_is_joined_before_compensating_only_its_unused_work(
    async_engine: AsyncEngine,
    sources: Sources,
    monkeypatch: pytest.MonkeyPatch,
    closing: bool,
) -> None:
    @asynccontextmanager
    async def connection() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine) as db:
            yield db
            await db.commit()

    monkeypatch.setattr("src.infrastructure.streaming.reservation_work.get_db_context", connection)
    entered, proceed = asyncio.Event(), asyncio.Event()
    async with AsyncSession(async_engine) as db:
        admission = await ConversationExecutionRepository(db).admit(
            sources.annex,
            run_id=uuid4().hex,
            stream_id=uuid4().hex,
            worker_id=uuid4(),
            kind=ExecutionKind.LIVE,
        )
        assert isinstance(admission, RunAdmission)
        await db.commit()
        repo = ConversationReservationRepository(db)
        work = (
            await repo.begin_closing(admission, worker_id=uuid4())
            if closing
            else await repo.begin(admission, worker_id=uuid4(), purpose="opening")
        )
        real_commit = db.commit

        async def delayed_commit() -> None:
            entered.set()
            await proceed.wait()
            await real_commit()

        monkeypatch.setattr(db, "commit", delayed_commit)
        task = asyncio.create_task(commit_work(db, work))
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        assert not task.done()
        proceed.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 10)
    async with connection() as fresh:
        busy = await ConversationExecutionRepository(fresh).active_for_owner(
            sources.annex.owner_id, kind=ExecutionKind.LIVE
        )
        if closing:
            assert busy is not None and busy.phase == ExecutionPhase.RUNNING
        else:
            assert busy is None
        assert not await ConversationReservationRepository(fresh).outstanding_workers(admission)


async def test_cancellation_after_fork_commit_before_session_exit_leaves_no_unused_child(
    async_engine: AsyncEngine,
    sources: Sources,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with AsyncSession(async_engine) as db:
        admission = await ConversationExecutionRepository(db).admit(
            sources.annex,
            run_id=uuid4().hex,
            stream_id=uuid4().hex,
            worker_id=uuid4(),
            kind=ExecutionKind.LIVE,
        )
        assert isinstance(admission, RunAdmission)
        parent = await ConversationReservationRepository(db).begin_closing(
            admission, worker_id=uuid4()
        )
        await db.commit()
    exiting = asyncio.Event()
    first = True

    @asynccontextmanager
    async def connection() -> AsyncIterator[AsyncSession]:
        nonlocal first
        pause = first
        first = False
        async with AsyncSession(async_engine) as db:
            yield db
            if pause:
                exiting.set()
                await asyncio.Event().wait()
            await db.commit()

    monkeypatch.setattr("src.infrastructure.streaming.reservation_work.get_db_context", connection)
    task = asyncio.create_task(fork_relay(parent))
    await asyncio.wait_for(exiting.wait(), 10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 10)
    async with AsyncSession(async_engine) as fresh:
        repo = ConversationReservationRepository(fresh)
        assert await repo.outstanding_workers(admission) == frozenset({parent.worker_id})
        assert await repo.finish(parent)
        await fresh.commit()
        assert await repo.is_closed(admission)
