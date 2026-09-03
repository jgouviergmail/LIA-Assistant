"""Presence banking against a real PostgreSQL (ADR-214 amendment 2026-09-03).

- ``bump_activity_hour`` is a server-side atomic UPSERT: two concurrent
  bumps of the same hour leave exactly one count of 1; a bump on an hour the
  message sources already counted never lowers it (GREATEST).
- ``fetch_feedback_activity`` reads thumbs by ``feedback_at`` from both
  notification tables and nothing else — a sent notification is invisible.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.habits.models import UserActivityDay
from src.domains.habits.repository import HabitsRepository
from src.domains.heartbeat.models import HeartbeatNotification
from src.domains.interests.models import InterestNotification
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def owner(async_session: AsyncSession) -> User:
    user = User(
        email=f"presence-{uuid.uuid4().hex[:10]}@example.com",
        hashed_password="x",
        full_name="Presence Owner",
        is_active=True,
        is_verified=True,
    )
    async_session.add(user)
    await async_session.commit()
    return user


async def _hour_counts(session: AsyncSession, user_id: uuid.UUID, day: date) -> dict[str, int]:
    row = (
        await session.execute(
            select(UserActivityDay).where(
                UserActivityDay.user_id == user_id, UserActivityDay.local_date == day
            )
        )
    ).scalar_one()
    return dict(row.hour_counts)


async def test_bump_creates_then_marks_without_inflating(
    async_session: AsyncSession, owner: User
) -> None:
    repo = HabitsRepository(async_session)
    day = date(2026, 9, 3)
    await repo.upsert_activity_days(owner.id, {day: {9: 4}})
    await async_session.commit()

    await repo.bump_activity_hour(owner.id, day, 14)
    await repo.bump_activity_hour(owner.id, day, 14)
    await repo.bump_activity_hour(owner.id, day, 9)  # already counted 4 by messages
    await async_session.commit()

    assert await _hour_counts(async_session, owner.id, day) == {"9": 4, "14": 1}


async def test_two_workers_banking_the_same_hour_lose_nothing() -> None:
    """Two independent sessions (two workers) bump the same new day/hour
    concurrently: one INSERT wins, the other updates — never a duplicate key
    error, never a lost row. The user is committed through its own session so
    every worker connection sees it (the test-scoped session is transactional)."""
    day = date(2026, 9, 4)
    async with get_db_context() as db:
        user = User(
            email=f"presence-workers-{uuid.uuid4().hex[:10]}@example.com",
            hashed_password="x",
            full_name="Presence Workers",
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        await db.commit()
        user_id = user.id

    async def _worker(hour: int) -> None:
        async with get_db_context() as db:
            await HabitsRepository(db).bump_activity_hour(user_id, day, hour)
            await db.commit()

    try:
        await asyncio.gather(_worker(8), _worker(8), _worker(21))
        async with get_db_context() as db:
            assert await _hour_counts(db, user_id, day) == {"8": 1, "21": 1}
    finally:
        async with get_db_context() as db:
            row = await db.get(User, user_id)
            if row is not None:
                await db.delete(row)  # cascades user_activity_days
                await db.commit()


async def test_feedback_source_reads_only_stamped_thumbs(
    async_session: AsyncSession, owner: User
) -> None:
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    async_session.add(
        HeartbeatNotification(
            user_id=owner.id,
            run_id=f"hb-{uuid.uuid4().hex}",
            content="sent, never rated",
            content_hash="h1",
            sources_used="[]",
        )
    )
    async_session.add(
        HeartbeatNotification(
            user_id=owner.id,
            run_id=f"hb-{uuid.uuid4().hex}",
            content="rated",
            content_hash="h2",
            sources_used="[]",
            user_feedback="thumbs_up",
            feedback_at=now - timedelta(hours=3),
        )
    )
    async_session.add(
        InterestNotification(
            user_id=owner.id,
            run_id=f"in-{uuid.uuid4().hex}",
            content="rated interest",
            content_hash="h3",
            source="interest",
            user_feedback="thumbs_down",
            feedback_at=now - timedelta(hours=5),
        )
    )
    await async_session.commit()

    days = await HabitsRepository(async_session).fetch_feedback_activity(
        owner.id, "UTC", now - timedelta(days=1)
    )

    counted = sum(sum(hours.values()) for hours in days.values())
    assert counted == 2  # the un-rated notification is invisible
