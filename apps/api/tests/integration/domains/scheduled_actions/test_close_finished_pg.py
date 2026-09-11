"""A routine that will never fire again stops looking active (ADR-281, lot 5).

A series ends three ways: its ``SeriesEnd`` date is reached, its
``after_count`` runs out, or its single occurrence is consumed. All three land
on the same state — ``next_trigger_at`` NULL, which the model already defines
as « nothing follows » — and the due query excludes it by construction, since
``NULL <= now()`` is UNKNOWN in SQL.

What nothing did was CLOSE such a row. It stayed ``is_enabled = true`` and
``status = 'active'`` for ever, indistinguishable on screen from one the person
had paused. That is the whole of this sweep, and it deliberately reads the end
from the trigger the recurrence engine arms rather than from a column of its
own: an ``expires_at`` beside a ``SeriesEnd`` would be a second authority on
when a routine stops, and only one of the two would be shown, edited and told
in six languages.

Proven against a real server: a unit test that mocks the session never executes
the statement, and this one turns on what SQL does with NULL.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.domains.scheduled_actions.models import ScheduledAction, ScheduledActionStatus
from src.domains.scheduled_actions.repository import ScheduledActionRepository
from src.domains.users.models import User

pytestmark = pytest.mark.integration

# Anchored on the REAL clock: ``get_and_lock_due_actions`` reads its own, so a
# fixed literal in the future would make every routine "not due yet" — and a
# literal in the past would make this suite start failing on the day it names.


@pytest_asyncio.fixture
async def committed(async_engine: Any, test_database_url: str) -> Any:
    """A sessionmaker whose writes really commit, plus its clean-up."""
    engine = create_async_engine(test_database_url, echo=False)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    marker = f"watch_close_{uuid4().hex}@test.local"
    yield maker, marker
    async with maker() as session:
        await session.execute(delete(User).where(User.email == marker))
        await session.commit()
    await engine.dispose()


async def _seed(
    maker: Any,
    email: str,
    *,
    next_trigger_at: datetime | None,
    status: str = ScheduledActionStatus.ACTIVE.value,
    is_enabled: bool = True,
) -> UUID:
    """One account and one routine in the state under test."""
    async with maker() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            user = User(email=email, hashed_password="x", is_active=True, is_verified=True)
            session.add(user)
            await session.flush()
        action = ScheduledAction(
            user_id=user.id,
            title="Watch",
            action_prompt="tell me when Marie replies",
            recurrence={"freq": "daily", "interval": 1, "anchor_date": "2026-09-01"},
            user_timezone="UTC",
            next_trigger_at=next_trigger_at,
            status=status,
            is_enabled=is_enabled,
        )
        session.add(action)
        await session.commit()
        return UUID(str(action.id))


async def _due_ids(maker: Any) -> set[UUID]:
    async with maker() as session:
        due = await ScheduledActionRepository(session).get_and_lock_due_actions(limit=50)
        ids = {UUID(str(action.id)) for action in due}
        await session.rollback()
        return ids


async def _close(maker: Any) -> int:
    async with maker() as session:
        closed = await ScheduledActionRepository(session).close_finished()
        await session.commit()
        return closed


async def _row(maker: Any, action_id: UUID) -> ScheduledAction:
    async with maker() as session:
        row = await session.get(ScheduledAction, action_id)
        assert row is not None
        return row


class TestWhatSqlDoesWithANullTrigger:
    """The premise the whole design rests on, verified rather than assumed."""

    async def test_a_finished_series_is_not_due(self, committed: Any) -> None:
        """``NULL <= now()`` is UNKNOWN, so the row is excluded with no filter."""
        maker, marker = committed
        action_id = await _seed(maker, marker, next_trigger_at=None)

        assert action_id not in await _due_ids(maker)

    async def test_a_routine_still_armed_is_due_exactly_as_before(self, committed: Any) -> None:
        maker, marker = committed
        action_id = await _seed(
            maker, marker, next_trigger_at=datetime.now(UTC) - timedelta(minutes=1)
        )

        assert action_id in await _due_ids(maker)


class TestClosingWhatHasNoFutureLeft:
    async def test_it_is_disabled_rather_than_deleted(self, committed: Any) -> None:
        """The person must be able to see what they had posted."""
        maker, marker = committed
        action_id = await _seed(maker, marker, next_trigger_at=None)

        assert await _close(maker) == 1
        row = await _row(maker, action_id)
        assert row.is_enabled is False
        assert row.status == ScheduledActionStatus.COMPLETED.value

    async def test_closing_is_idempotent(self, committed: Any) -> None:
        """The sweep runs every tick; the second pass must find nothing."""
        maker, marker = committed
        await _seed(maker, marker, next_trigger_at=None)

        assert await _close(maker) == 1
        assert await _close(maker) == 0

    async def test_a_routine_still_armed_is_never_closed(self, committed: Any) -> None:
        maker, marker = committed
        action_id = await _seed(
            maker, marker, next_trigger_at=datetime.now(UTC) + timedelta(hours=2)
        )

        assert await _close(maker) == 0
        assert (await _row(maker, action_id)).is_enabled is True

    async def test_a_routine_the_person_paused_is_left_alone(self, committed: Any) -> None:
        """A pause is somebody's decision; « finished » would overwrite it."""
        maker, marker = committed
        action_id = await _seed(maker, marker, next_trigger_at=None, is_enabled=False)

        assert await _close(maker) == 0
        assert (await _row(maker, action_id)).status == ScheduledActionStatus.ACTIVE.value

    async def test_a_routine_mid_run_is_left_alone(self, committed: Any) -> None:
        """EXECUTING carries a NULL trigger between the run and the re-arm.

        Closing it there would end a routine in the middle of its own tick.
        """
        maker, marker = committed
        action_id = await _seed(
            maker,
            marker,
            next_trigger_at=None,
            status=ScheduledActionStatus.EXECUTING.value,
        )

        assert await _close(maker) == 0
        assert (await _row(maker, action_id)).status == ScheduledActionStatus.EXECUTING.value
