"""A reminder is claimed one at a time, and the claim holds no lock (ADR-304).

Proved on a real PostgreSQL server with two independent actors, because the
guarantees live in the database: ``FOR UPDATE SKIP LOCKED`` keeps two workers
off the same row, the committed PROCESSING status is the claim once the lock is
gone, the settlement only touches a row whose claim still stands, and a claim a
crash abandoned is released on ``updated_at``. The scheduler used to lock a
batch of up to 100 rows and keep them — and one transaction — for the whole
batch of model calls and pushes.

Every row here is REALLY committed (the per-test SAVEPOINT isolation hides a
row from every other connection) and removed with its account at the end.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.domains.reminders.models import Reminder, ReminderStatus
from src.domains.reminders.repository import ReminderRepository
from src.domains.users.models import User

pytestmark = pytest.mark.integration

Maker = async_sessionmaker[AsyncSession]

ONCE = {
    "freq": "once",
    "interval": 1,
    "anchor_date": "2026-09-22",
    "times": {"mode": "at", "at": [{"hour": 9, "minute": 0}]},
}


@pytest_asyncio.fixture
async def committed(async_engine: Any, test_database_url: str) -> AsyncIterator[tuple[Maker, str]]:
    """A sessionmaker whose writes really commit, and the account's clean-up."""
    engine = create_async_engine(test_database_url, echo=False)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    marker = f"reminder_claims_{uuid4().hex}@example.com"
    yield maker, marker
    async with maker() as session:
        await session.execute(delete(User).where(User.email == marker))
        await session.commit()
    await engine.dispose()


async def _seed(maker: Maker, email: str, count: int) -> list[UUID]:
    """An account with ``count`` reminders due a minute ago, oldest first."""
    async with maker() as session:
        user = User(email=email, hashed_password="x", is_active=True, is_verified=True)
        session.add(user)
        await session.flush()
        due = datetime.now(UTC) - timedelta(minutes=1)
        reminders = [
            Reminder(
                user_id=user.id,
                content=f"r{index}",
                original_message=f"remind me r{index}",
                recurrence=ONCE,
                trigger_at=due + timedelta(seconds=index),
                user_timezone="UTC",
            )
            for index in range(count)
        ]
        session.add_all(reminders)
        await session.commit()
        return [UUID(str(reminder.id)) for reminder in reminders]


async def _status(maker: Maker, reminder_id: UUID) -> str:
    async with maker() as session:
        row = await session.execute(select(Reminder.status).where(Reminder.id == reminder_id))
        return str(row.scalar_one())


async def test_two_workers_never_claim_the_same_reminder(committed: tuple[Maker, str]) -> None:
    maker, marker = committed
    first_id, second_id = await _seed(maker, marker, 2)

    async with maker() as worker_a, maker() as worker_b:
        claimed_a = await ReminderRepository(worker_a).claim_next_due()
        # A has not committed yet: its row is locked, so B skips it.
        claimed_b = await ReminderRepository(worker_b).claim_next_due()
        await worker_a.commit()
        await worker_b.commit()

    assert claimed_a is not None and claimed_b is not None
    assert {claimed_a.id, claimed_b.id} == {first_id, second_id}
    assert await _status(maker, first_id) == ReminderStatus.PROCESSING.value
    assert await _status(maker, second_id) == ReminderStatus.PROCESSING.value


async def test_a_committed_claim_holds_no_lock_and_is_not_claimed_again(
    committed: tuple[Maker, str],
) -> None:
    maker, marker = committed
    (reminder_id,) = await _seed(maker, marker, 1)

    async with maker() as worker:
        assert await ReminderRepository(worker).claim_next_due() is not None
        await worker.commit()

    async with maker() as other:
        # No lock survives the claim: another writer takes the row at once.
        await other.execute(
            select(Reminder.id).where(Reminder.id == reminder_id).with_for_update(nowait=True)
        )
        # And the claim is the status: nothing is due any more.
        assert await ReminderRepository(other).claim_next_due() is None
        await other.rollback()


async def test_the_settlement_only_touches_a_standing_claim(committed: tuple[Maker, str]) -> None:
    maker, marker = committed
    claimed_id, pending_id = await _seed(maker, marker, 2)

    async with maker() as worker:
        claim = await ReminderRepository(worker).claim_next_due()
        await worker.commit()
    assert claim is not None and claim.id == claimed_id

    async with maker() as settler:
        repo = ReminderRepository(settler)
        assert await repo.get_processing_for_update(claimed_id) is not None
        # A row nobody claimed (or one released meanwhile) is not settled.
        assert await repo.get_processing_for_update(pending_id) is None
        await settler.rollback()


async def test_an_abandoned_claim_is_released_and_a_live_one_is_kept(
    committed: tuple[Maker, str],
) -> None:
    maker, marker = committed
    abandoned_id, live_id = await _seed(maker, marker, 2)

    async with maker() as worker:
        repo = ReminderRepository(worker)
        assert await repo.claim_next_due() is not None
        assert await repo.claim_next_due() is not None
        await worker.commit()
    # The first claim is twenty minutes old: its worker died.
    async with maker() as clock:
        await clock.execute(
            update(Reminder)
            .where(Reminder.id == abandoned_id)
            .values(updated_at=datetime.now(UTC) - timedelta(minutes=20))
        )
        await clock.commit()

    async with maker() as recovery:
        released = await ReminderRepository(recovery).recover_stale_processing(10)
        await recovery.commit()

    assert released == 1
    assert await _status(maker, abandoned_id) == ReminderStatus.PENDING.value
    assert await _status(maker, live_id) == ReminderStatus.PROCESSING.value
