"""A routine its account's usage ceiling stood aside, on a real server.

The unit tests mock the session, so they never execute the statements: the
fenced re-arm, the run row under its real CHECK, the ledger rewritten as a NEW
JSONB value. What must hold on PostgreSQL:

- the routine is re-armed on its own clock and freed, and NOTHING counts toward
  the pause a series of failures ends in (ADR-272);
- a time routine's skipped slot carries ``skipped_quota``; a condition routine
  writes no row and says why on its ledger, which its card reads back;
- a tick that lost its reservation writes neither.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.time_utils import now_utc
from src.domains.scheduled_actions.models import (
    ScheduledAction,
    ScheduledActionRun,
    ScheduledActionStatus,
    ScheduledRunOutcome,
)
from src.domains.scheduled_actions.repository import ScheduledActionRepository
from src.domains.scheduled_actions.schemas import ScheduledActionResponse
from src.domains.users.models import User
from src.infrastructure.scheduler.scheduled_action_executor import _stand_aside_for_quota, _Tick
from src.infrastructure.scheduler.scheduled_action_notices import RoutineNotice

pytestmark = pytest.mark.integration

#: Due long before anything another test could leave behind: a reservation
#: takes the oldest due row, and it must be this module's.
_LONG_DUE = datetime(2000, 1, 1, tzinfo=UTC)


@pytest_asyncio.fixture
async def maker(async_engine: Any, test_database_url: str) -> Any:
    """A sessionmaker whose writes really commit, plus its clean-up."""
    engine = create_async_engine(test_database_url, echo=False)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    marker = f"quota_{uuid4().hex}@test.local"
    yield sessions, marker
    async with sessions() as session:
        await session.execute(delete(User).where(User.email == marker))
        await session.commit()
    await engine.dispose()


async def _routine(sessions: Any, email: str, **columns: Any) -> UUID:
    async with sessions() as session:
        user = User(email=email, hashed_password="x", is_active=True, is_verified=True)
        session.add(user)
        await session.flush()
        action = ScheduledAction(
            user_id=user.id,
            title="Quota",
            action_prompt="say hello",
            user_timezone="UTC",
            next_trigger_at=_LONG_DUE,
            status=ScheduledActionStatus.ACTIVE.value,
            is_enabled=True,
            **columns,
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


async def _stand_aside(sessions: Any, action_id: UUID, token: UUID) -> Any:
    """The tick's settle, on a session of its own, committed as the executor commits it."""
    async with sessions() as session:
        repo = ScheduledActionRepository(session)
        action = await repo.get_by_id(action_id)
        assert action is not None
        tick = _Tick(
            db=session,
            repo=repo,
            action=action,
            token=token,
            due_at=_LONG_DUE,
            started_at=now_utc(),
        )
        ended = await _stand_aside_for_quota(tick, unserved_state=None)
        await session.commit()
        return ended


async def _read(sessions: Any, action_id: UUID) -> tuple[ScheduledAction, list[ScheduledActionRun]]:
    async with sessions() as session:
        action = await session.get(ScheduledAction, action_id)
        runs = list(
            (
                await session.execute(
                    select(ScheduledActionRun).where(
                        ScheduledActionRun.scheduled_action_id == action_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert action is not None
        return action, runs


_DAILY = {
    "freq": "daily",
    "interval": 1,
    "anchor_date": "2026-09-01",
    "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
}


async def test_a_time_routine_is_rearmed_with_its_reason_and_no_failure(maker: Any) -> None:
    sessions, email = maker
    action_id = await _routine(sessions, email, recurrence=_DAILY)
    token = await _reserve(sessions, action_id)

    ended = await _stand_aside(sessions, action_id, token)

    action, runs = await _read(sessions, action_id)
    assert ended.notice is RoutineNotice.QUOTA and ended.text == ""
    # Freed and re-armed on its own clock, still enabled.
    assert action.status == ScheduledActionStatus.ACTIVE.value
    assert action.execution_token is None and action.is_enabled is True
    assert action.next_trigger_at is not None and action.next_trigger_at > now_utc()
    # Not a failure, not an execution.
    assert (action.consecutive_failures, action.last_error, action.execution_count) == (0, None, 0)
    (run,) = runs
    assert run.outcome is ScheduledRunOutcome.SKIPPED_QUOTA
    assert (run.attempts, run.error, run.slot_at) == (0, None, _LONG_DUE)


async def test_a_condition_routine_says_it_on_its_ledger_and_writes_no_row(maker: Any) -> None:
    sessions, email = maker
    action_id = await _routine(
        sessions,
        email,
        trigger_kind="condition",
        condition_config={"type": "task_overdue"},
        condition_state={"seen": ["k-seen"], "last_fired_at": "2026-11-01T08:00:00+00:00"},
    )
    token = await _reserve(sessions, action_id)

    ended = await _stand_aside(sessions, action_id, token)

    action, runs = await _read(sessions, action_id)
    assert ended.notice is RoutineNotice.QUOTA
    assert runs == []
    assert action.status == ScheduledActionStatus.ACTIVE.value
    assert action.consecutive_failures == 0
    state = action.condition_state
    assert state is not None
    assert state["last_check_error"] == "quota_blocked"
    # Nothing was read: what the routine had seen and served is kept.
    assert state["seen"] == ["k-seen"]
    assert state["last_fired_at"] == "2026-11-01T08:00:00+00:00"
    # The card reads the reason back through the API schema.
    assert ScheduledActionResponse.model_validate(action).last_check_error == "quota_blocked"


async def test_a_tick_that_lost_its_reservation_writes_nothing(maker: Any) -> None:
    sessions, email = maker
    action_id = await _routine(sessions, email, recurrence=_DAILY)
    await _reserve(sessions, action_id)

    ended = await _stand_aside(sessions, action_id, uuid4())

    action, runs = await _read(sessions, action_id)
    assert ended.notice is None
    assert runs == []
    # Still the other tick's: reserved, on its original slot.
    assert action.status == ScheduledActionStatus.EXECUTING.value
    assert action.next_trigger_at == _LONG_DUE
