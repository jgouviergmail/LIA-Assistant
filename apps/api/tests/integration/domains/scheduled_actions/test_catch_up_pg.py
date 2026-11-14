"""An occurrence given up as too late, and one kept armed for a busy account, on a real server.

The unit tests mock the session, so they never execute the statements: the
fenced re-arm on an instant the tick chose, the run row under its real CHECK.
What must hold on PostgreSQL (ADR-265 amendment 2026-11-12 b):

- an occurrence reached past its window leaves ``skipped_late`` on ITS slot,
  counts nothing against the routine, and the routine is freed on the most
  recent occurrence that may still start;
- an occurrence that found its account busy is freed on the SAME instant, with
  no row: the scheduler's next pass finds it due again;
- a tick that lost its reservation writes neither.

The routine lives in a zone far from UTC: its 08:00 is 19:00 UTC of the day
before, so a slot computed on the wrong calendar cannot pass.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

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
from src.domains.scheduled_actions.trigger import DueOccurrence, TriggerPlan
from src.domains.users.models import User
from src.infrastructure.scheduler.scheduled_action_executor import (
    _give_up_late,
    _Tick,
    _wait_for_account,
)

pytestmark = pytest.mark.integration

AUCKLAND = "Pacific/Auckland"
_ZONE = ZoneInfo(AUCKLAND)
_DAILY_AT_EIGHT = {
    "freq": "daily",
    "interval": 1,
    "anchor_date": "2026-11-01",
    "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
}


def _local(day: int, hour: int, minute: int = 0) -> datetime:
    """A wall time of November 2026 in Auckland, as the UTC instant it is."""
    return datetime(2026, 11, day, hour, minute, tzinfo=_ZONE).astimezone(UTC)


#: The occurrence the outage swallowed, and the instant the scheduler came back:
#: twenty minutes after the NEXT day's occurrence.
_MISSED = _local(10, 8)
_BACK = _local(11, 8, 20)


@pytest_asyncio.fixture
async def maker(async_engine: Any, test_database_url: str) -> Any:
    """A sessionmaker whose writes really commit, plus its clean-up."""
    engine = create_async_engine(test_database_url, echo=False)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    marker = f"catchup_{uuid4().hex}@test.local"
    yield sessions, marker
    async with sessions() as session:
        await session.execute(delete(User).where(User.email == marker))
        await session.commit()
    await engine.dispose()


async def _reserved_routine(sessions: Any, email: str, *, due_at: datetime) -> tuple[UUID, UUID]:
    """A daily routine a tick holds, due at ``due_at``."""
    token = uuid4()
    async with sessions() as session:
        user = User(email=email, hashed_password="x", is_active=True, is_verified=True)
        session.add(user)
        await session.flush()
        action = ScheduledAction(
            user_id=user.id,
            title="Catch-up",
            action_prompt="say hello",
            user_timezone=AUCKLAND,
            recurrence=_DAILY_AT_EIGHT,
            next_trigger_at=due_at,
            status=ScheduledActionStatus.EXECUTING.value,
            execution_token=token,
            is_enabled=True,
        )
        session.add(action)
        await session.commit()
        return action.id, token


async def _settle(
    sessions: Any,
    action_id: UUID,
    token: UUID,
    *,
    due_at: datetime,
    started_at: datetime,
    occurrence: DueOccurrence | None = None,
    wait: bool = False,
) -> Any:
    """One of the tick's two settles, on a session of its own, committed as the executor does."""
    async with sessions() as session:
        repo = ScheduledActionRepository(session)
        action = await repo.get_by_id(action_id)
        assert action is not None
        due = occurrence or TriggerPlan.of(action).due_occurrence(
            due_at=due_at, started_at=started_at
        )
        assert due is not None
        tick = _Tick(
            db=session,
            repo=repo,
            action=action,
            token=token,
            due_at=due_at,
            started_at=started_at,
            occurrence=due,
        )
        answer = await (_wait_for_account(tick) if wait else _give_up_late(tick, due))
        await session.commit()
        return answer


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


async def test_a_missed_occurrence_is_recorded_and_the_latest_one_armed(maker: Any) -> None:
    sessions, email = maker
    action_id, token = await _reserved_routine(sessions, email, due_at=_MISSED)

    await _settle(sessions, action_id, token, due_at=_MISSED, started_at=_BACK)

    action, runs = await _read(sessions, action_id)
    # Freed on the occurrence twenty minutes old — today's, on the routine's
    # own calendar — which the scheduler's next pass serves.
    assert action.status == ScheduledActionStatus.ACTIVE.value
    assert action.execution_token is None and action.is_enabled is True
    assert action.next_trigger_at == _local(11, 8)
    # Not a failure, not an execution.
    assert (action.consecutive_failures, action.last_error, action.execution_count) == (0, None, 0)
    (run,) = runs
    assert run.outcome is ScheduledRunOutcome.SKIPPED_LATE
    assert (run.attempts, run.error, run.manual, run.slot_at) == (0, None, False, _MISSED)


async def test_past_every_window_the_next_occurrence_is_armed(maker: Any) -> None:
    sessions, email = maker
    action_id, token = await _reserved_routine(sessions, email, due_at=_MISSED)

    await _settle(sessions, action_id, token, due_at=_MISSED, started_at=_local(11, 14))

    action, runs = await _read(sessions, action_id)
    assert action.next_trigger_at == _local(12, 8)
    assert [run.outcome for run in runs] == [ScheduledRunOutcome.SKIPPED_LATE]


async def test_a_busy_account_leaves_the_same_occurrence_due_and_writes_no_row(
    maker: Any,
) -> None:
    sessions, email = maker
    action_id, token = await _reserved_routine(sessions, email, due_at=_MISSED)
    waited_for = DueOccurrence(
        at=_MISSED, late_after=None, retry_until=now_utc() + timedelta(hours=1)
    )

    kept = await _settle(
        sessions,
        action_id,
        token,
        due_at=_MISSED,
        started_at=now_utc(),
        occurrence=waited_for,
        wait=True,
    )

    action, runs = await _read(sessions, action_id)
    assert kept is True
    assert runs == []
    # Freed on the instant it was due for: due again at the next pass.
    assert action.status == ScheduledActionStatus.ACTIVE.value
    assert action.execution_token is None
    assert action.next_trigger_at == _MISSED
    assert (action.consecutive_failures, action.execution_count) == (0, 0)


async def test_a_wait_that_is_over_leaves_the_routine_to_its_stand_aside(maker: Any) -> None:
    sessions, email = maker
    action_id, token = await _reserved_routine(sessions, email, due_at=_MISSED)
    over = DueOccurrence(at=_MISSED, late_after=None, retry_until=now_utc())

    kept = await _settle(
        sessions,
        action_id,
        token,
        due_at=_MISSED,
        started_at=now_utc(),
        occurrence=over,
        wait=True,
    )

    action, runs = await _read(sessions, action_id)
    assert kept is False
    # Untouched: the caller records why and re-arms on the next occurrence.
    assert runs == []
    assert action.status == ScheduledActionStatus.EXECUTING.value
    assert action.execution_token == token


@pytest.mark.parametrize("wait", [False, True])
async def test_a_tick_that_lost_its_reservation_writes_nothing(maker: Any, wait: bool) -> None:
    sessions, email = maker
    action_id, token = await _reserved_routine(sessions, email, due_at=_MISSED)
    waited_for = DueOccurrence(
        at=_MISSED, late_after=_MISSED, retry_until=now_utc() + timedelta(hours=1)
    )

    await _settle(
        sessions,
        action_id,
        uuid4(),
        due_at=_MISSED,
        started_at=_BACK,
        occurrence=waited_for,
        wait=wait,
    )

    action, runs = await _read(sessions, action_id)
    assert runs == []
    # Still the other tick's: reserved, on its original slot.
    assert action.status == ScheduledActionStatus.EXECUTING.value
    assert action.execution_token == token
    assert action.next_trigger_at == _MISSED
