"""Independent SQL connections prove account admission, revocation and rollback."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_execution import (
    ExecutionKind,
    ExecutionPhase,
    ExecutionRevoked,
    RunAdmission,
    RunBusy,
    RunEnd,
)
from src.core.conversation_target import ConversationRef
from src.domains.conversations.execution_models import ConversationExecution
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.models import Conversation
from tests.fixtures.persisted_runtimes import persist_runtime_targets

pytestmark = pytest.mark.integration


@pytest.fixture
async def targets(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> tuple[ConversationRef, ConversationRef, ConversationRef]:
    """A/B share an account; C has its own, and all runtimes differ from row IDs."""
    first, foreign = await persist_runtime_targets(async_engine, committed_user_ids, count=2)
    second = replace(first, id=uuid4(), runtime_id=uuid4())
    async with AsyncSession(async_engine) as db:
        db.add(
            Conversation(
                id=second.id,
                user_id=second.owner_id,
                kind=second.kind,
                title="Second",
                revision=second.revision,
                runtime_id=second.runtime_id,
            )
        )
        await db.commit()
    return first, second, foreign


async def admit(
    engine: AsyncEngine, target: ConversationRef, *, kind: ExecutionKind = ExecutionKind.GRAPH
) -> RunAdmission | RunBusy:
    """Each actor owns its own short transaction and boot identity."""
    async with AsyncSession(engine, expire_on_commit=False) as db:
        result = await ConversationExecutionRepository(db).admit(
            target,
            run_id=str(uuid4()),
            stream_id=str(uuid4()),
            worker_id=uuid4(),
            kind=kind,
            relayed=True,
        )
        await db.commit()
        return result


async def test_two_workers_cannot_admit_two_discussions_of_one_account(
    async_engine: AsyncEngine, targets: tuple[ConversationRef, ConversationRef, ConversationRef]
) -> None:
    first, second, foreign = targets
    results = await asyncio.gather(admit(async_engine, first), admit(async_engine, second))
    winners = [result for result in results if isinstance(result, RunAdmission)]
    losers = [result for result in results if isinstance(result, RunBusy)]
    assert len(winners) == len(losers) == 1
    assert losers[0].target == winners[0].target
    assert isinstance(await admit(async_engine, foreign), RunAdmission)


@pytest.mark.parametrize(
    "phase", [ExecutionPhase.RUNNING, ExecutionPhase.DRAINING, ExecutionPhase.RECOVERING]
)
async def test_age_and_recovery_never_transfer_authority(
    async_engine: AsyncEngine,
    targets: tuple[ConversationRef, ConversationRef, ConversationRef],
    phase: ExecutionPhase,
) -> None:
    admission = await admit(async_engine, targets[0])
    assert isinstance(admission, RunAdmission)
    async with AsyncSession(async_engine) as db:
        await db.execute(
            update(ConversationExecution)
            .where(ConversationExecution.id == admission.activity_id)
            .values(phase=phase, heartbeat_at=datetime.now(UTC) - timedelta(days=365))
        )
        await db.commit()
    busy = await admit(async_engine, targets[1])
    assert isinstance(busy, RunBusy) and busy.phase == phase


async def test_live_reservation_coexists_with_its_graph_but_not_another_live(
    async_engine: AsyncEngine, targets: tuple[ConversationRef, ConversationRef, ConversationRef]
) -> None:
    assert isinstance(await admit(async_engine, targets[0], kind=ExecutionKind.LIVE), RunAdmission)
    assert isinstance(await admit(async_engine, targets[0]), RunAdmission)
    assert isinstance(await admit(async_engine, targets[1], kind=ExecutionKind.LIVE), RunBusy)


async def test_only_current_owner_can_close_and_an_old_finalizer_cannot_close_the_next_run(
    async_engine: AsyncEngine, targets: tuple[ConversationRef, ConversationRef, ConversationRef]
) -> None:
    first = await admit(async_engine, targets[0])
    assert isinstance(first, RunAdmission)
    async with AsyncSession(async_engine) as db:
        repo = ConversationExecutionRepository(db)
        assert not await repo.close_owned(replace(first, owner_token=uuid4()), end=RunEnd.NORMAL)
        assert not await repo.close_owned(replace(first, worker_id=uuid4()), end=RunEnd.NORMAL)
        assert not await repo.close_owned(replace(first, fence=first.fence + 1), end=RunEnd.NORMAL)
        assert await repo.mark_draining(first)
        await db.commit()
    assert isinstance(await admit(async_engine, targets[1]), RunBusy)
    async with AsyncSession(async_engine) as db:
        assert await ConversationExecutionRepository(db).close_owned(first, end=RunEnd.NORMAL)
        await db.commit()
    second = await admit(async_engine, targets[1])
    assert isinstance(second, RunAdmission) and second.fence > first.fence
    async with AsyncSession(async_engine) as db:
        repo = ConversationExecutionRepository(db)
        assert not await repo.close_owned(first, end=RunEnd.NORMAL)
        await db.commit()
        active = await repo.active_for_owner(second.target.owner_id)
        assert active is not None and active.stream_id == second.stream_id


async def test_rollback_releases_admission_without_persisting_a_claim(
    async_engine: AsyncEngine, targets: tuple[ConversationRef, ConversationRef, ConversationRef]
) -> None:
    async with AsyncSession(async_engine) as db:
        result = await ConversationExecutionRepository(db).admit(
            targets[0], run_id=str(uuid4()), stream_id=str(uuid4()), worker_id=uuid4()
        )
        assert isinstance(result, RunAdmission)
        await db.rollback()
    assert isinstance(await admit(async_engine, targets[1]), RunAdmission)


@pytest.mark.parametrize("field", ["owner_id", "revision", "runtime_id"])
async def test_stale_or_foreign_target_cannot_reserve_execution(
    async_engine: AsyncEngine,
    targets: tuple[ConversationRef, ConversationRef, ConversationRef],
    field: str,
) -> None:
    target = targets[0]
    invalid = {
        "owner_id": replace(target, owner_id=targets[2].owner_id),
        "revision": replace(target, revision=target.revision - 1),
        "runtime_id": replace(target, runtime_id=uuid4()),
    }[field]
    with pytest.raises(ExecutionRevoked):
        await admit(async_engine, invalid)
    assert isinstance(await admit(async_engine, target), RunAdmission)


async def test_old_heartbeat_cannot_reopen_a_closed_execution(
    async_engine: AsyncEngine, targets: tuple[ConversationRef, ConversationRef, ConversationRef]
) -> None:
    admission = await admit(async_engine, targets[0])
    assert isinstance(admission, RunAdmission)
    async with AsyncSession(async_engine) as db:
        repo = ConversationExecutionRepository(db)
        assert await repo.mark_recovering(admission)
        assert not await repo.touch(admission)
        assert await repo.close_owned(admission, end=RunEnd.NORMAL)
        await db.commit()
        assert not await repo.touch(admission)
        row = await db.scalar(
            select(ConversationExecution).where(ConversationExecution.id == admission.activity_id)
        )
        assert row is not None and row.phase == ExecutionPhase.CLOSED
        assert row.closed_at is not None


async def test_lost_retag_acknowledgement_cannot_orphan_an_unused_owned_admission(
    async_engine: AsyncEngine,
    targets: tuple[ConversationRef, ConversationRef, ConversationRef],
) -> None:
    admission = await admit(async_engine, targets[0])
    assert isinstance(admission, RunAdmission)
    async with AsyncSession(async_engine) as db:
        await ConversationExecutionRepository(db).retag_run(admission, "original-hitl-billing-run")
        await db.commit()
    # The acknowledgement was lost: the owner still holds its original DTO,
    # but the activity/token/fence are unchanged and no producer started.
    async with AsyncSession(async_engine) as db:
        assert await ConversationExecutionRepository(db).close_owned(admission, end=RunEnd.NORMAL)
        await db.commit()
    assert isinstance(await admit(async_engine, targets[1]), RunAdmission)
