"""Native habit refusals and typed payloads apply before context consumption."""

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.habits.discussion_source import HabitDiscussionSource
from src.domains.habits.models import UserHabit
from src.domains.shared.discussion_sources import SourceKey
from src.domains.users.models import User
from tests.integration.domains.proactive_discussions.test_memory_portrait_sources import (
    NOW,
    read_request,
)

pytestmark = pytest.mark.integration


async def seed_habits(engine: AsyncEngine, owner: UUID) -> None:
    async with AsyncSession(engine) as db:
        user = await db.get(User, owner)
        assert user is not None
        user.habits_enabled = True
        for index, status in enumerate(("active", "paused", "blocked")):
            db.add(
                UserHabit(
                    user_id=owner,
                    kind="recurring_request",
                    key=f"fictional-music-{index}",
                    status=status,
                    last_observed_at=NOW,
                    payload={
                        "version": 1,
                        "shape": "intermittent",
                        "trigger_hour": 9.5,
                        "days_of_week": [],
                        "distinct_days": 8,
                        "occurrences": 9,
                        "usual_intent": "Find a fictional score",
                    },
                )
            )
        await db.commit()


async def test_blocked_and_paused_rows_are_excluded_before_page_and_count(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "habits_enabled", True)
    await seed_habits(async_engine, discussion_owner)
    result = await HabitDiscussionSource().read(read_request(discussion_owner, SourceKey.HABITS))
    assert result.total == 1 and result.complete and len(result.items) == 1
    assert "Find a fictional score" in result.items[0].excerpt
    assert result.items[0].occurred_at is None and result.items[0].assertion == "inferred"
    assert "intermittent" in result.items[0].excerpt


async def test_global_habit_consent_is_live(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "habits_enabled", True)
    await seed_habits(async_engine, discussion_owner)
    async with AsyncSession(async_engine) as db:
        user = await db.get(User, discussion_owner)
        assert user is not None
        user.habits_enabled = False
        await db.commit()
    result = await HabitDiscussionSource().read(read_request(discussion_owner, SourceKey.HABITS))
    assert result.status == "disabled" and not result.items


async def test_unknown_payload_version_is_not_guessed(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "habits_enabled", True)
    await seed_habits(async_engine, discussion_owner)
    async with AsyncSession(async_engine) as db:
        row = await db.scalar(
            select(UserHabit).where(
                UserHabit.user_id == discussion_owner, UserHabit.status == "active"
            )
        )
        assert row is not None
        row.payload = {**row.payload, "version": 999}
        await db.commit()
    with pytest.raises(ValueError):
        await HabitDiscussionSource().read(read_request(discussion_owner, SourceKey.HABITS))
