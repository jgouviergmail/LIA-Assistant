"""The run history against PostgreSQL (ADR-265).

What a unit double cannot prove: the CHECK-backed outcome column accepts every
enum value and refuses others, both cascades fire, the week read returns the
account's rows only and oldest first, and the purge removes by age.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.scheduled_actions.models import (
    ScheduledAction,
    ScheduledActionRun,
    ScheduledRunOutcome,
)
from src.domains.scheduled_actions.run_repository import ScheduledActionRunRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

T0 = datetime(2026, 8, 3, 6, 0, tzinfo=UTC)


async def _make_user(db: AsyncSession) -> uuid.UUID:
    from src.domains.users.models import User

    user = User(
        email=f"runs-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x" * 60,
        full_name="Runs",
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    await db.flush()
    return user.id


async def _make_action(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    action = ScheduledAction(
        user_id=user_id,
        title="Morning",
        action_prompt="brief me",
        days_of_week=[1, 2, 3, 4, 5],
        trigger_hour=8,
        trigger_minute=0,
        user_timezone="Europe/Paris",
        next_trigger_at=T0,
    )
    db.add(action)
    await db.flush()
    return action.id


async def _record(
    db: AsyncSession,
    action_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    started: datetime,
    outcome: ScheduledRunOutcome = ScheduledRunOutcome.SUCCESS,
) -> ScheduledActionRun:
    return await ScheduledActionRunRepository(db).record(
        scheduled_action_id=action_id,
        user_id=user_id,
        slot_at=started,
        started_at=started,
        ended_at=started + timedelta(seconds=30),
        outcome=outcome,
        attempts=1,
        manual=False,
    )


class TestOutcomeColumn:
    @pytest.mark.parametrize("outcome", list(ScheduledRunOutcome))
    async def test_every_declared_outcome_is_accepted(
        self, db_session: AsyncSession, outcome: ScheduledRunOutcome
    ) -> None:
        user_id = await _make_user(db_session)
        action_id = await _make_action(db_session, user_id)
        row = await _record(db_session, action_id, user_id, started=T0, outcome=outcome)
        await db_session.refresh(row)
        assert row.outcome is outcome

    async def test_an_undeclared_value_is_refused_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        user_id = await _make_user(db_session)
        action_id = await _make_action(db_session, user_id)
        with pytest.raises(DBAPIError):
            await db_session.execute(
                text(
                    "INSERT INTO scheduled_action_runs "
                    "(id, scheduled_action_id, user_id, started_at, ended_at, outcome, "
                    "attempts, manual) VALUES (:id, :a, :u, :t, :t, 'exploded', 1, false)"
                ),
                {"id": uuid.uuid4(), "a": action_id, "u": user_id, "t": T0},
            )
        await db_session.rollback()


class TestCascades:
    async def test_deleting_the_routine_removes_its_runs(self, db_session: AsyncSession) -> None:
        user_id = await _make_user(db_session)
        action_id = await _make_action(db_session, user_id)
        await _record(db_session, action_id, user_id, started=T0)

        await db_session.execute(
            text("DELETE FROM scheduled_actions WHERE id = :id"), {"id": action_id}
        )

        left = (
            (
                await db_session.execute(
                    select(ScheduledActionRun).where(
                        ScheduledActionRun.scheduled_action_id == action_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert left == []


class TestWeekRead:
    async def test_lists_the_account_only_from_the_bound_oldest_first(
        self, db_session: AsyncSession
    ) -> None:
        user_id = await _make_user(db_session)
        other_id = await _make_user(db_session)
        action_id = await _make_action(db_session, user_id)
        other_action = await _make_action(db_session, other_id)
        await _record(db_session, action_id, user_id, started=T0 + timedelta(days=2))
        await _record(db_session, action_id, user_id, started=T0)
        await _record(db_session, action_id, user_id, started=T0 - timedelta(days=9))
        await _record(db_session, other_action, other_id, started=T0)

        rows = await ScheduledActionRunRepository(db_session).list_since(
            user_id, T0 - timedelta(days=1)
        )

        assert [r.started_at for r in rows] == [T0, T0 + timedelta(days=2)]
        assert {r.user_id for r in rows} == {user_id}


class TestPurge:
    async def test_removes_by_age_across_accounts(self, db_session: AsyncSession) -> None:
        user_id = await _make_user(db_session)
        action_id = await _make_action(db_session, user_id)
        await _record(db_session, action_id, user_id, started=T0 - timedelta(days=100))
        await _record(db_session, action_id, user_id, started=T0)

        purged = await ScheduledActionRunRepository(db_session).purge_older_than(
            T0 - timedelta(days=90)
        )

        assert purged == 1
        remaining = (
            (
                await db_session.execute(
                    select(ScheduledActionRun.started_at).where(
                        ScheduledActionRun.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert remaining == [T0]
