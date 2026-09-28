"""The service writes routines the one-clock CHECK accepts — on a real PostgreSQL.

Found at the first HTTP proof of ADR-322 on dev: a condition routine created
through the service was refused by ``ck_scheduled_actions_one_clock``. A
Python ``None`` on a JSONB column is persisted as the JSON ``null``, which
``IS NULL`` does not match — so a routine « with no recurrence » had one, as
far as the table could tell. Every unit test passed: none of them executes the
INSERT. This file does, for both clocks and for the switches between them.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay
from src.core.time_utils import now_utc
from src.domains.scheduled_actions.schemas import (
    ConditionConfig,
    ScheduledActionCreate,
    ScheduledActionUpdate,
)
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.users.models import User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

EVERY_DAY_AT_EIGHT = RecurrenceSpec(
    freq="daily",
    times=DailyTimes(mode="at", at=(TimeOfDay(hour=8, minute=0),)),
    anchor_date=date(2026, 9, 1),
)


async def _user(session: AsyncSession) -> UUID:
    user = User(email=f"one_clock_{uuid4().hex}@example.com", hashed_password="x", is_active=True)
    session.add(user)
    await session.flush()
    return UUID(str(user.id))


async def _stored(session: AsyncSession, action_id: UUID) -> Any:
    """What the TABLE holds — SQL NULL told apart from the JSON null."""
    return (
        await session.execute(
            text(
                "SELECT trigger_kind, recurrence IS NULL AS no_schedule, "
                "condition_config IS NULL AS no_condition, condition_config, "
                "condition_state IS NULL AS no_ledger FROM scheduled_actions WHERE id = :id"
            ),
            {"id": action_id},
        )
    ).one()


async def test_a_condition_routine_is_stored_with_no_schedule(async_session: AsyncSession) -> None:
    user_id = await _user(async_session)
    until = now_utc().astimezone(ZoneInfo("Europe/Paris")).date() + timedelta(days=3)

    action = await ScheduledActionService(async_session).create(
        user_id,
        ScheduledActionCreate(
            title="Watch",
            action_prompt="tell me",
            trigger_kind="condition",
            condition_config=ConditionConfig(type="task_overdue", until=until),
        ),
        "Europe/Paris",
    )
    await async_session.flush()

    row = await _stored(async_session, action.id)
    assert (row.trigger_kind, row.no_schedule, row.no_condition) == ("condition", True, False)
    assert row.condition_config == {"type": "task_overdue", "until": until.isoformat()}


async def test_a_scheduled_routine_is_stored_with_no_condition(async_session: AsyncSession) -> None:
    user_id = await _user(async_session)

    action = await ScheduledActionService(async_session).create(
        user_id,
        ScheduledActionCreate(
            title="Brief", action_prompt="brief me", recurrence=EVERY_DAY_AT_EIGHT
        ),
        "Europe/Paris",
    )
    await async_session.flush()

    row = await _stored(async_session, action.id)
    assert (row.trigger_kind, row.no_schedule, row.no_condition) == ("time", False, True)


async def test_switching_clocks_both_ways_keeps_one_clock(async_session: AsyncSession) -> None:
    user_id = await _user(async_session)
    service = ScheduledActionService(async_session)
    action = await service.create(
        user_id,
        ScheduledActionCreate(
            title="Brief", action_prompt="brief me", recurrence=EVERY_DAY_AT_EIGHT
        ),
        "Europe/Paris",
    )
    await async_session.flush()

    await service.update(
        action.id,
        user_id,
        ScheduledActionUpdate(
            trigger_kind="condition", condition_config=ConditionConfig(type="document_added")
        ),
    )
    await async_session.flush()
    row = await _stored(async_session, action.id)
    assert (row.trigger_kind, row.no_schedule, row.no_condition) == ("condition", True, False)

    await service.update(
        action.id,
        user_id,
        ScheduledActionUpdate(trigger_kind="time", recurrence=EVERY_DAY_AT_EIGHT),
    )
    await async_session.flush()
    row = await _stored(async_session, action.id)
    assert (row.trigger_kind, row.no_schedule, row.no_condition, row.no_ledger) == (
        "time",
        False,
        True,
        True,
    )
