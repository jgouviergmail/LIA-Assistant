"""A routine's reservation is held by its token, at load and at the settle (point 19).

Two ticks can hold one routine in turn: the recovery frees a reservation older
than its threshold, and the next tick reserves it again under a new token. The
first tick, if still alive, must then neither run nor settle: its token no
longer holds the row. Renewing the reservation right before the model runs
makes the recovery count from the run's real start, not from the reservation.

Proven against a real server, with two independent actors: a unit test that
mocks the session never executes the conditional statements.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.domains.scheduled_actions.models import ScheduledAction, ScheduledActionStatus
from src.domains.scheduled_actions.repository import ScheduledActionRepository
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def maker(async_engine: Any, test_database_url: str) -> Any:
    """A sessionmaker whose writes really commit, plus its clean-up."""
    engine = create_async_engine(test_database_url, echo=False)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    marker = f"fence_{uuid4().hex}@test.local"
    yield sessions, marker
    async with sessions() as session:
        await session.execute(delete(User).where(User.email == marker))
        await session.commit()
    await engine.dispose()


async def _due_routine(sessions: Any, email: str) -> UUID:
    async with sessions() as session:
        user = User(email=email, hashed_password="x", is_active=True, is_verified=True)
        session.add(user)
        await session.flush()
        action = ScheduledAction(
            user_id=user.id,
            title="Fence",
            action_prompt="say hello",
            recurrence={"freq": "daily", "interval": 1, "anchor_date": "2026-09-01"},
            user_timezone="UTC",
            # Due before anything another test could leave behind: the
            # reservation below takes one row, and it must be this one.
            next_trigger_at=datetime(2000, 1, 1, tzinfo=UTC),
            status=ScheduledActionStatus.ACTIVE.value,
            is_enabled=True,
        )
        session.add(action)
        await session.commit()
        return action.id


async def _reserve(sessions: Any, action_id: UUID) -> UUID:
    """One tick's reservation, exactly as the scheduler takes it."""
    async with sessions() as session:
        (action,) = await ScheduledActionRepository(session).get_and_lock_due_actions(limit=1)
        await session.commit()
    assert action.id == action_id and action.execution_token is not None
    return action.execution_token


async def _age(sessions: Any, action_id: UUID, minutes: int) -> None:
    async with sessions() as session:
        await session.execute(
            update(ScheduledAction)
            .where(ScheduledAction.id == action_id)
            .values(updated_at=datetime.now(UTC) - timedelta(minutes=minutes))
        )
        await session.commit()


async def test_a_superseded_tick_neither_renews_nor_settles(maker: Any) -> None:
    sessions, email = maker
    action_id = await _due_routine(sessions, email)
    first = await _reserve(sessions, action_id)

    # The first tick outlives the threshold; the recovery frees its row and the
    # next tick reserves it again.
    await _age(sessions, action_id, minutes=60)
    async with sessions() as session:
        freed = await ScheduledActionRepository(session).recover_stale_executing(
            older_than=datetime.now(UTC) - timedelta(minutes=30)
        )
        await session.commit()
    assert freed == 1
    second = await _reserve(sessions, action_id)
    assert second != first

    async with sessions() as session:
        repo = ScheduledActionRepository(session)
        assert await repo.renew_reservation(action_id, first) is False
        assert await repo.lock_reserved(action_id, first) is None
        held = await repo.lock_reserved(action_id, second)
        assert held is not None and held.execution_token == second
        await session.commit()


async def test_a_renewed_reservation_is_counted_from_the_run_s_start(maker: Any) -> None:
    sessions, email = maker
    action_id = await _due_routine(sessions, email)
    token = await _reserve(sessions, action_id)
    await _age(sessions, action_id, minutes=60)

    async with sessions() as session:
        assert await ScheduledActionRepository(session).renew_reservation(action_id, token)
        await session.commit()
    async with sessions() as session:
        freed = await ScheduledActionRepository(session).recover_stale_executing(
            older_than=datetime.now(UTC) - timedelta(minutes=30)
        )
        status = (
            await session.execute(
                select(ScheduledAction.status).where(ScheduledAction.id == action_id)
            )
        ).scalar_one()
        await session.commit()

    assert freed == 0
    assert status == ScheduledActionStatus.EXECUTING.value


@pytest.mark.parametrize("replacement", [False, True])
async def test_a_late_empty_condition_check_preserves_the_current_holder(
    maker: Any, monkeypatch: pytest.MonkeyPatch, replacement: bool
) -> None:
    from src.infrastructure.scheduler.condition_evaluators import ConditionVerdict
    from src.infrastructure.scheduler.scheduled_action_executor import _condition_gate

    sessions, email = maker
    action_id = await _due_routine(sessions, email)
    first = await _reserve(sessions, action_id)
    second: list[UUID | None] = [None]
    new_status = (
        ScheduledActionStatus.EXECUTING.value if replacement else ScheduledActionStatus.ACTIVE.value
    )

    async def source(*args: Any, **kwargs: Any) -> ConditionVerdict:
        # The source answers only after a second committed actor cancelled or
        # replaced the reservation. The first session still carries its old ORM row.
        async with sessions() as other:
            assert await ScheduledActionRepository(other).release_manual_execution(
                action_id, args[0].id, first
            )
            await other.commit()
        if replacement:
            second[0] = await _reserve(sessions, action_id)
        return ConditionVerdict()

    monkeypatch.setattr(
        "src.infrastructure.scheduler.condition_evaluators.evaluate_condition", source
    )
    async with sessions() as session:
        action = await session.get(ScheduledAction, action_id)
        assert action is not None
        due_at = action.next_trigger_at
        await _condition_gate(
            session,
            ScheduledActionRepository(session),
            action,
            action.user_id,
            started_at=datetime.now(UTC),
            due_at=due_at,
            execution_token=first,
        )
        await session.commit()

    async with sessions() as session:
        current = await session.get(ScheduledAction, action_id)
        assert current is not None
        assert current.status == new_status
        assert current.execution_token == second[0]
        assert current.next_trigger_at == due_at
        assert current.condition_state is None
