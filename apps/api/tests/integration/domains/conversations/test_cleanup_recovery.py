"""Cleanup authority survives crashes and refuses every stale owner transition."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from prometheus_client import REGISTRY
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.config import settings
from src.core.conversation_execution import RunAdmission
from src.core.conversation_target import ConversationKind, ConversationRef
from src.domains.conversations.cleanup_contracts import (
    CleanupPhase,
    CleanupState,
    ConversationAction,
)
from src.domains.conversations.cleanup_models import ConversationOperation
from src.domains.conversations.cleanup_repository import ConversationCleanupRepository
from src.domains.conversations.cleanup_runner import ConversationCleanupRunner
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.infrastructure.scheduler import conversation_cleanup
from tests.fixtures.learning_sources import Sources
from tests.fixtures.learning_sources import sources as sources

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("changes", [{"new_revision": None}, {"owner_token": uuid4()}])
async def test_database_refuses_partial_revision_or_partial_claim(
    async_engine: AsyncEngine,
    operation_id: UUID,
    changes: dict[str, object],
) -> None:
    async with AsyncSession(async_engine) as db, db.begin():
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(
                    update(ConversationOperation)
                    .where(ConversationOperation.id == operation_id)
                    .values(**changes)
                )


@pytest.fixture
async def operation_id(async_engine: AsyncEngine) -> AsyncIterator[UUID]:
    """Own the operational receipt explicitly: an account CASCADE must not erase it."""
    identity = uuid4()
    async with AsyncSession(async_engine) as db:
        db.add(
            ConversationOperation(
                id=identity,
                user_id=uuid4(),
                request_id=uuid4(),
                conversation_id=uuid4(),
                action=ConversationAction.RESET,
                conversation_kind=ConversationKind.SECONDARY,
                old_revision=4,
                new_revision=5,
                runtime_id=uuid4(),
                attachment_ids=[],
            )
        )
        await db.commit()
    yield identity
    async with AsyncSession(async_engine) as db:
        await db.execute(delete(ConversationOperation).where(ConversationOperation.id == identity))
        await db.commit()


async def test_expired_claim_cannot_renew_advance_fail_or_close_a_new_owner(
    async_engine: AsyncEngine,
    operation_id: UUID,
) -> None:
    async with AsyncSession(async_engine) as first, AsyncSession(async_engine) as second:
        a, b = ConversationCleanupRepository(first), ConversationCleanupRepository(second)
        old = await a.claim(lease_seconds=60, operation_id=operation_id)
        await first.commit()
        assert old is not None
        assert await b.claim(lease_seconds=60, operation_id=operation_id) is None
        await second.commit()
        await first.execute(
            update(ConversationOperation)
            .where(ConversationOperation.id == operation_id)
            .values(claim_until=datetime.now(UTC) - timedelta(seconds=1))
        )
        await first.commit()
        assert not await a.renew(old, lease_seconds=60)
        await first.commit()
        new = await b.claim(lease_seconds=60, operation_id=operation_id)
        await second.commit()
        assert new is not None and new.fence > old.fence and new.owner_token != old.owner_token
        assert not await a.advance(old)
        assert not await a.fail(old, error_code="cleanup_failed", max_attempts=3, retry_seconds=5)
        await first.commit()
        assert await b.advance(new)
        await second.commit()
        row = await first.get(ConversationOperation, operation_id, populate_existing=True)
        assert (
            row is not None
            and row.phase == CleanupPhase.CONTEXT
            and row.state == CleanupState.RUNNING
        )


async def test_failure_keeps_the_exact_phase_and_escalates_without_expiring_debt(
    async_engine: AsyncEngine,
    operation_id: UUID,
) -> None:
    async with AsyncSession(async_engine) as db:
        repo = ConversationCleanupRepository(db)
        claim = await repo.claim(lease_seconds=60, operation_id=operation_id)
        await db.commit()
        assert claim is not None
        assert await repo.fail(claim, error_code="cleanup_refused", max_attempts=1, retry_seconds=5)
        await db.commit()
        row = await db.get(ConversationOperation, operation_id, populate_existing=True)
        assert row is not None
        assert (row.state, row.phase, row.owner_token, row.completed_at) == (
            CleanupState.NEEDS_ATTENTION,
            CleanupPhase.CHECKPOINT,
            None,
            None,
        )
        assert await repo.claim(lease_seconds=60, operation_id=operation_id) is None
        await db.commit()
        assert await repo.expire_completed(before=datetime.now(UTC) + timedelta(days=100)) == 0
        await db.commit()
        assert (
            await db.scalar(
                select(ConversationOperation.id).where(ConversationOperation.id == operation_id)
            )
            == operation_id
        )


async def test_only_all_explicit_phases_close_the_operation(
    async_engine: AsyncEngine,
    operation_id: UUID,
) -> None:
    async with AsyncSession(async_engine) as db:
        repo = ConversationCleanupRepository(db)
        claim = await repo.claim(lease_seconds=60, operation_id=operation_id)
        await db.commit()
        assert claim is not None
        for phase in (
            CleanupPhase.CHECKPOINT,
            CleanupPhase.CONTEXT,
            CleanupPhase.PENDING,
            CleanupPhase.FILES,
        ):
            current = replace(claim, phase=phase)
            assert await repo.advance(current)
            await db.commit()
            assert not await repo.advance(current)
            await db.commit()
        row = await db.get(ConversationOperation, operation_id, populate_existing=True)
        assert row is not None and row.state == CleanupState.SUCCEEDED
        assert row.completed_at is not None and row.claim_until is None


async def test_explicit_recovery_cannot_take_a_live_claim_or_repeat_the_logical_act(
    async_engine: AsyncEngine,
    operation_id: UUID,
) -> None:
    async with AsyncSession(async_engine) as db:
        repo = ConversationCleanupRepository(db)
        claim = await repo.claim(lease_seconds=60, operation_id=operation_id)
        await db.commit()
        assert claim is not None
        row = await db.get(ConversationOperation, operation_id)
        assert row is not None
        request_id = row.request_id
        current = await repo.retry_requested(row.user_id, request_id)
        assert current.owner_token == claim.owner_token and current.fence == claim.fence
        assert await repo.advance(claim)
        await db.commit()
        advanced = replace(claim, phase=CleanupPhase.CONTEXT)
        assert await repo.fail(
            advanced, error_code="cleanup_refused", max_attempts=1, retry_seconds=5
        )
        await db.commit()
        current = await repo.retry_requested(claim.target.owner_id, request_id)
        assert current.state == CleanupState.PENDING and current.attempts == 0
        assert current.phase == CleanupPhase.CONTEXT
        assert (current.runtime_id, current.old_revision, current.new_revision) == (
            claim.target.runtime_id,
            4,
            5,
        )
        await db.commit()


class ControlledRuntime:
    """Only external I/O is controlled; durable claims use independent real sessions."""

    def __init__(self) -> None:
        self.seen: list[CleanupPhase] = []
        self.refused: CleanupPhase | None = None
        self.gate: asyncio.Event | None = None
        self.started = asyncio.Event()
        self.raise_failure = False

    async def prepare_owner(self, owner: UUID) -> None:
        """No Live record exists in this cleanup fixture."""

    async def purge_checkpoint(self, target: ConversationRef) -> bool:
        self.seen.append(CleanupPhase.CHECKPOINT)
        self.started.set()
        if self.raise_failure:
            raise OSError("Injected native cleanup failure")
        if self.gate is not None:
            await self.gate.wait()
        return self.refused != CleanupPhase.CHECKPOINT

    async def purge_tool_context(self, target: ConversationRef) -> bool:
        self.seen.append(CleanupPhase.CONTEXT)
        return self.refused != CleanupPhase.CONTEXT

    async def purge_pending(self, target: ConversationRef) -> bool:
        self.seen.append(CleanupPhase.PENDING)
        return self.refused != CleanupPhase.PENDING


async def test_the_sweep_exposes_durable_debt_and_recovery_then_clears_both(
    async_engine: AsyncEngine,
    operation_id: UUID,
    sources: Sources,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator sees terminal debt and a quarantined execution until their real settlement."""
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    monkeypatch.setattr(conversation_cleanup, "AsyncSessionLocal", factory)
    monkeypatch.setattr(conversation_cleanup, "NativeRuntimeCleanup", ControlledRuntime)
    async with factory() as db:
        repo = ConversationCleanupRepository(db)
        claim = await repo.claim(lease_seconds=60, operation_id=operation_id)
        assert claim is not None
        assert await repo.fail(claim, error_code="cleanup_refused", max_attempts=1, retry_seconds=5)
        row = await db.get(ConversationOperation, operation_id)
        assert row is not None
        row.created_at = datetime.now(UTC) - timedelta(hours=1)
        earliest = row.created_at.timestamp()
        executions = ConversationExecutionRepository(db)
        admission = await executions.admit(
            sources.annex, run_id=uuid4().hex, stream_id=uuid4().hex, worker_id=uuid4()
        )
        assert isinstance(admission, RunAdmission)
        assert await executions.mark_recovering(admission)
        await db.commit()

    await conversation_cleanup.cleanup_conversations()
    labels = {"state": "needs_attention"}
    first = REGISTRY.get_sample_value("conversation_cleanup_snapshot_timestamp_seconds")
    assert first is not None and first >= earliest
    assert REGISTRY.get_sample_value("conversation_cleanup_operations", labels) == 1
    assert (
        REGISTRY.get_sample_value("conversation_cleanup_oldest_timestamp_seconds", labels)
        == earliest
    )
    assert REGISTRY.get_sample_value("conversation_executions_recovering") == 1

    async with factory() as db:
        await ConversationCleanupRepository(db).retry_requested(row.user_id, row.request_id)
        assert await ConversationExecutionRepository(db).close_recovered(admission)
        await db.commit()
    result = await conversation_cleanup.cleanup_conversations()
    assert result["completed"] >= 1
    assert REGISTRY.get_sample_value("conversation_cleanup_operations", labels) == 0
    assert REGISTRY.get_sample_value("conversation_cleanup_oldest_timestamp_seconds", labels) == 0
    assert REGISTRY.get_sample_value("conversation_executions_recovering") == 0


async def test_runner_stops_at_explicit_failure_and_resumes_the_failed_phase(
    async_engine: AsyncEngine,
    operation_id: UUID,
) -> None:
    runtime = ControlledRuntime()
    runtime.refused = CleanupPhase.CONTEXT
    runner = ConversationCleanupRunner(async_sessionmaker(async_engine), runtime)
    assert not await runner.run_one(operation_id=operation_id)
    assert runtime.seen == [CleanupPhase.CHECKPOINT, CleanupPhase.CONTEXT]
    async with AsyncSession(async_engine) as db:
        row = await db.get(ConversationOperation, operation_id)
        assert row is not None and row.state == CleanupState.RETRY_WAIT
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    runtime.refused = None
    assert await runner.run_one(operation_id=operation_id)
    assert runtime.seen == [
        CleanupPhase.CHECKPOINT,
        CleanupPhase.CONTEXT,
        CleanupPhase.CONTEXT,
        CleanupPhase.PENDING,
    ]


async def test_cancellation_joins_the_phase_and_leaves_recoverable_debt(
    async_engine: AsyncEngine,
    operation_id: UUID,
) -> None:
    runtime = ControlledRuntime()
    runtime.gate = asyncio.Event()
    runner = ConversationCleanupRunner(async_sessionmaker(async_engine), runtime)
    task = asyncio.create_task(runner.run_one(operation_id=operation_id))
    await asyncio.wait_for(runtime.started.wait(), timeout=10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with AsyncSession(async_engine) as db:
        row = await db.get(ConversationOperation, operation_id)
        assert row is not None and row.state == CleanupState.RETRY_WAIT
        assert row.phase == CleanupPhase.CHECKPOINT and row.error_code == "cleanup_cancelled"
    assert runtime.seen == [CleanupPhase.CHECKPOINT]


async def test_native_exception_is_recorded_and_never_masks_cleanup_debt(
    async_engine: AsyncEngine,
    operation_id: UUID,
) -> None:
    runtime = ControlledRuntime()
    runtime.raise_failure = True
    runner = ConversationCleanupRunner(async_sessionmaker(async_engine), runtime)
    assert not await runner.run_one(operation_id=operation_id)
    async with AsyncSession(async_engine) as db:
        row = await db.get(ConversationOperation, operation_id)
        assert row is not None and row.error_code == "cleanup_failed"
        assert row.state == CleanupState.RETRY_WAIT


async def test_wait_holds_no_transaction_and_lost_lease_stops_later_effects(
    async_engine: AsyncEngine,
    operation_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "conversation_cleanup_lease_seconds", 3)
    runtime = ControlledRuntime()
    runtime.gate = asyncio.Event()
    runner = ConversationCleanupRunner(async_sessionmaker(async_engine), runtime)
    idle = text(
        "SELECT pid FROM pg_stat_activity WHERE datname = current_database() AND state = 'idle in transaction'"
    )
    async with async_engine.connect() as observer:
        baseline = set((await observer.execute(idle)).scalars())
    task = asyncio.create_task(runner.run_one(operation_id=operation_id))
    try:
        await asyncio.wait_for(runtime.started.wait(), timeout=10)
        async with async_engine.connect() as observer:
            current = set((await observer.execute(idle)).scalars())
        assert current <= baseline
        async with AsyncSession(async_engine) as db:
            await db.execute(
                update(ConversationOperation)
                .where(ConversationOperation.id == operation_id)
                .values(claim_until=datetime.now(UTC) - timedelta(seconds=1))
            )
            await db.commit()
            successor = await ConversationCleanupRepository(db).claim(
                lease_seconds=60, operation_id=operation_id
            )
            await db.commit()
            assert successor is not None
        assert not await asyncio.wait_for(task, timeout=10)
        assert runtime.seen == [CleanupPhase.CHECKPOINT]
        async with AsyncSession(async_engine) as db:
            row = await db.get(ConversationOperation, operation_id)
            assert row is not None and row.owner_token == successor.owner_token
            assert row.state == CleanupState.RUNNING and row.phase == CleanupPhase.CHECKPOINT
    finally:
        runtime.gate.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
