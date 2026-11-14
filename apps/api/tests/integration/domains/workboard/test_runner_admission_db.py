"""A ticket's durable claim precedes remote admission gates and owns its start event."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.usage_limits.service import UsageLimitService
from src.domains.users.models import User
from src.domains.workboard.constants import AssigneeKind, RunOutcome, TicketPriority, TicketStatus
from src.domains.workboard.models import WorkboardTicket
from src.infrastructure.async_utils import cancel_and_join
from src.infrastructure.scheduler import workboard_runner

pytestmark = pytest.mark.integration


async def test_quota_check_holds_no_transaction_and_sees_a_committed_claim(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = uuid4()
    committed_user_ids.append(owner)
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        db.add(
            User(
                id=owner,
                email=f"runner-{owner}@example.com",
                hashed_password="unused",
                is_active=True,
            )
        )
        await db.flush()
        ticket = WorkboardTicket(
            owner_user_id=owner,
            title="A controlled ticket",
            status=TicketStatus.TODO.value,
            priority=TicketPriority.MEDIUM.value,
            assignee_kind=AssigneeKind.LIA.value,
            position=0,
            created_by="user",
            status_changed_at=datetime.now(UTC),
        )
        db.add(ticket)
        await db.commit()
        checked: list[bool] = []

        async def quota(user_id: UUID, *, layer: str) -> bool:
            assert user_id == owner
            assert not db.in_transaction(), "No SQL transaction may surround the quota's Redis call"
            async with AsyncSession(async_engine) as observer:
                row = (
                    await observer.execute(
                        select(
                            WorkboardTicket.status,
                            WorkboardTicket.run_claimed_at,
                        ).where(WorkboardTicket.id == ticket.id)
                    )
                ).one()
            assert row.status == TicketStatus.IN_PROGRESS.value
            assert row.run_claimed_at is not None
            checked.append(True)
            return False

        monkeypatch.setattr(UsageLimitService, "is_user_blocked_for_llm", quota)
        monkeypatch.setattr(
            workboard_runner, "build_ticket_brief", AsyncMock(return_value="Controlled brief")
        )
        prepared = await workboard_runner._claim_and_prepare(db, datetime.now(UTC))
        assert prepared is not None and prepared.ticket_id == ticket.id
        assert checked == [True]


@pytest.mark.parametrize("phase", ["quota", "run"])
async def test_a_cancelled_worker_closes_its_committed_ticket_claim(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    owner = uuid4()
    committed_user_ids.append(owner)
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        db.add(
            User(
                id=owner,
                email=f"cancelled-runner-{owner}@example.com",
                hashed_password="unused",
                is_active=True,
            )
        )
        await db.flush()
        ticket = WorkboardTicket(
            owner_user_id=owner,
            title="Interrupted ticket",
            status=TicketStatus.TODO.value,
            priority=TicketPriority.MEDIUM.value,
            assignee_kind=AssigneeKind.LIA.value,
            position=0,
            created_by="user",
            status_changed_at=datetime.now(UTC),
        )
        db.add(ticket)
        await db.commit()
    entered = asyncio.Event()
    closing = asyncio.Event()
    close_allowed = asyncio.Event()
    close_calls: list[str] = []
    abandon = workboard_runner._abandon_claim

    async def delayed_close(ticket_id: UUID, run_id: str) -> None:
        close_calls.append(run_id)
        closing.set()
        await close_allowed.wait()
        await abandon(ticket_id, run_id)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as owned:
            yield owned
            await owned.commit()

    async def wait_for_stop(*args: object, **kwargs: object) -> None:
        entered.set()
        await asyncio.Future[None]()

    monkeypatch.setattr(workboard_runner, "get_db_context", session)
    monkeypatch.setattr(workboard_runner, "_housekeeping", AsyncMock())
    monkeypatch.setattr(
        workboard_runner, "build_ticket_brief", AsyncMock(return_value="Controlled brief")
    )
    monkeypatch.setattr(
        UsageLimitService,
        "is_user_blocked_for_llm",
        wait_for_stop if phase == "quota" else AsyncMock(return_value=False),
    )
    monkeypatch.setattr(workboard_runner, "_run", wait_for_stop)
    monkeypatch.setattr(workboard_runner, "_abandon_claim", delayed_close)
    task = asyncio.create_task(workboard_runner.sweep_workboard_runs())
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        await asyncio.wait_for(closing.wait(), timeout=5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "The caller must join the same closer through repeated cancellation"
        close_allowed.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        close_allowed.set()
        await cancel_and_join(task)
    assert len(close_calls) == 1
    async with AsyncSession(async_engine) as observer:
        row = await observer.get(WorkboardTicket, ticket.id)
        assert row is not None
        assert row.run_claimed_at is None
        assert row.status == TicketStatus.IN_PROGRESS.value
        assert row.last_run_outcome == RunOutcome.FAILED.value
        assert row.run_count == 1
