"""A Live reservation outlives closing until every actual worker has settled."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_execution import (
    ExecutionKind,
    ExecutionPhase,
    ExecutionRevoked,
    RunAdmission,
)
from src.core.exceptions import ResourceConflictError
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.lifecycle import ConversationLifecycle
from src.domains.conversations.reservation_repository import ConversationReservationRepository
from src.domains.users.models import User
from src.infrastructure.streaming.live_recovery import (
    close_live_stopped,
    inspect_live,
    quarantine_live,
)
from tests.fixtures.learning_sources import Sources
from tests.fixtures.learning_sources import sources as sources

pytestmark = pytest.mark.integration


async def reserve(async_engine: AsyncEngine, sources: Sources) -> RunAdmission:
    async with AsyncSession(async_engine) as db:
        result = await ConversationExecutionRepository(db).admit(
            sources.annex,
            run_id=f"live_session_{uuid4().hex}",
            stream_id=uuid4().hex,
            worker_id=uuid4(),
            kind=ExecutionKind.LIVE,
        )
        assert isinstance(result, RunAdmission)
        await db.commit()
        return result


async def test_closing_joins_work_from_two_workers_before_releasing_the_discussion(
    async_engine: AsyncEngine, sources: Sources
) -> None:
    admission = await reserve(async_engine, sources)
    async with AsyncSession(async_engine) as db:
        repo = ConversationReservationRepository(db)
        first = await repo.begin(admission, worker_id=uuid4(), purpose="relay")
        second = await repo.begin(admission, worker_id=uuid4(), purpose="request")
        await db.commit()
        closing = await repo.begin_closing(admission, worker_id=uuid4())
        await db.commit()
        await repo.finish(closing)
        await repo.finish(first)
        await db.commit()
        busy = await ConversationExecutionRepository(db).active_for_owner(
            sources.annex.owner_id, kind=ExecutionKind.LIVE
        )
        assert busy is not None and busy.phase == ExecutionPhase.DRAINING
        await db.rollback()
        with pytest.raises(ResourceConflictError):
            await ConversationLifecycle(db).request_reset(
                sources.annex.owner_id,
                sources.annex.id,
                operation_id=uuid4(),
                expected_revision=sources.annex.revision,
            )
        await db.rollback()
        assert await repo.finish(second)
        assert not await repo.finish(second)
        await db.commit()
        assert (
            await ConversationExecutionRepository(db).active_for_owner(
                sources.annex.owner_id, kind=ExecutionKind.LIVE
            )
            is None
        )
        await db.rollback()
        await ConversationLifecycle(db).request_reset(
            sources.annex.owner_id,
            sources.annex.id,
            operation_id=uuid4(),
            expected_revision=sources.annex.revision,
        )


async def test_closing_refuses_new_requests_but_its_owned_final_relay_can_finish(
    async_engine: AsyncEngine, sources: Sources
) -> None:
    admission = await reserve(async_engine, sources)
    async with AsyncSession(async_engine) as db:
        repo = ConversationReservationRepository(db)
        closing = await repo.begin_closing(admission, worker_id=uuid4())
        child = await repo.fork(closing, worker_id=uuid4(), purpose="relay")
        await db.commit()
        with pytest.raises(ExecutionRevoked):
            await repo.begin(admission, worker_id=uuid4(), purpose="request")
        await db.rollback()
        await repo.require_current(child)
        await db.commit()
        assert await repo.finish(closing)
        await db.commit()
        assert await repo.finish(child)
        await db.commit()
        with pytest.raises(ExecutionRevoked):
            await repo.require_current(child)


async def test_a_stale_work_token_cannot_complete_or_publish(
    async_engine: AsyncEngine, sources: Sources
) -> None:
    admission = await reserve(async_engine, sources)
    async with AsyncSession(async_engine) as db:
        repo = ConversationReservationRepository(db)
        work = await repo.begin(admission, worker_id=uuid4(), purpose="request")
        await db.commit()
        stale = replace(work, owner_token=uuid4())
        assert not await repo.finish(stale)
        with pytest.raises(ExecutionRevoked):
            await repo.require_current(stale)
        await db.rollback()
        await repo.require_current(work)


async def test_unknown_opening_remains_occupied_without_automatic_replay(
    async_engine: AsyncEngine, sources: Sources
) -> None:
    admission = await reserve(async_engine, sources)
    async with AsyncSession(async_engine) as db:
        repo = ConversationReservationRepository(db)
        work = await repo.begin(admission, worker_id=uuid4(), purpose="opening")
        await db.commit()
        await repo.mark_unknown(work)
        await db.commit()
        await repo.mark_unknown(work)
        await db.commit()
        busy = await ConversationExecutionRepository(db).active_for_owner(
            sources.annex.owner_id, kind=ExecutionKind.LIVE
        )
        assert busy is not None and busy.phase == ExecutionPhase.RECOVERING
        with pytest.raises(ExecutionRevoked):
            await repo.require_current(work)


async def test_a_second_start_cannot_close_the_first_while_its_mint_is_still_running(
    async_engine: AsyncEngine,
    sources: Sources,
) -> None:
    admission = await reserve(async_engine, sources)
    async with AsyncSession(async_engine) as db:
        repo = ConversationReservationRepository(db)
        opening = await repo.begin(admission, worker_id=uuid4(), purpose="opening")
        await db.commit()
        with pytest.raises(ExecutionRevoked):
            await repo.begin_closing(admission, worker_id=uuid4())
        await db.rollback()
        assert await repo.finish(opening)
        await db.commit()
        closing = await repo.begin_closing(admission, worker_id=uuid4())
        assert await repo.finish(closing)
        await db.commit()
        assert await repo.is_closed(admission)


async def test_private_binding_and_reset_of_another_discussion(
    async_engine: AsyncEngine, sources: Sources
) -> None:
    admission = await reserve(async_engine, sources)
    async with AsyncSession(async_engine) as db:
        repo = ConversationReservationRepository(db)
        assert (
            await repo.load(sources.annex.owner_id, admission.activity_id, admission.stream_id)
            == admission
        )
        with pytest.raises(ExecutionRevoked):
            await repo.load(uuid4(), admission.activity_id, admission.stream_id)
        await db.rollback()
        await ConversationLifecycle(db).request_reset(
            sources.main.owner_id,
            sources.main.id,
            operation_id=uuid4(),
            expected_revision=sources.main.revision,
        )
        assert (
            await repo.load(sources.annex.owner_id, admission.activity_id, admission.stream_id)
            == admission
        )


async def test_deactivating_the_account_refuses_new_work_but_its_join_can_still_settle(
    async_engine: AsyncEngine,
    sources: Sources,
) -> None:
    admission = await reserve(async_engine, sources)
    async with AsyncSession(async_engine) as db:
        repo = ConversationReservationRepository(db)
        closing = await repo.begin_closing(admission, worker_id=uuid4())
        await db.commit()
        await db.execute(
            update(User).where(User.id == sources.annex.owner_id).values(is_active=False)
        )
        await db.commit()
        with pytest.raises(ExecutionRevoked):
            await repo.require_current(closing)
        await db.rollback()
        assert await repo.finish(closing)
        await db.commit()
        assert await repo.is_closed(admission)


async def test_idle_retirement_never_mistakes_an_outstanding_worker_for_a_dead_browser(
    async_engine: AsyncEngine,
    sources: Sources,
) -> None:
    admission = await reserve(async_engine, sources)
    async with AsyncSession(async_engine) as db:
        repo = ConversationReservationRepository(db)
        work = await repo.begin(admission, worker_id=uuid4(), purpose="request")
        await db.commit()
        assert not await repo.retire_idle(admission)
        assert await repo.finish(work)
        await db.commit()
        assert await repo.retire_idle(admission)
        await db.commit()
        with pytest.raises(ExecutionRevoked):
            await repo.begin(admission, worker_id=uuid4(), purpose="request")


async def test_quarantined_work_requires_every_actual_workers_stop_for_recovery(
    async_engine: AsyncEngine,
    sources: Sources,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @asynccontextmanager
    async def connection() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine) as db:
            yield db
            await db.commit()

    monkeypatch.setattr("src.infrastructure.streaming.live_recovery.get_db_context", connection)
    admission = await reserve(async_engine, sources)
    async with AsyncSession(async_engine) as db:
        repo = ConversationReservationRepository(db)
        first = await repo.begin(admission, worker_id=uuid4(), purpose="relay")
        second = await repo.begin(admission, worker_id=uuid4(), purpose="request")
        await db.commit()
        await repo.mark_unknown(first)
        await db.commit()
        assert not await repo.retire_idle(admission)
        with pytest.raises(ValueError):
            await repo.close_stopped(admission, stopped_workers={admission.worker_id})
        await db.rollback()
        assert await repo.finish(second)
        await db.commit()
        status = await inspect_live(admission.activity_id, admission.worker_id)
        assert status.outstanding_workers == frozenset({first.worker_id})
        assert await quarantine_live(admission.activity_id, admission.worker_id) == status
        closed = await close_live_stopped(
            admission.activity_id, admission.worker_id, stopped_workers={first.worker_id}
        )
        assert closed.phase == ExecutionPhase.CLOSED and not closed.outstanding_workers
        assert await repo.is_closed(admission)
        with pytest.raises(ExecutionRevoked):
            await repo.require_current(first)
