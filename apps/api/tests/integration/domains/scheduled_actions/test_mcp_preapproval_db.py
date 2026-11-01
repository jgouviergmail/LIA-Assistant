"""A routine's MCP pre-approval on a real PostgreSQL (spec 2026-10-29 D9).

The column is ``JSONB(none_as_null=True)``: a routine that pre-approves nothing
stores SQL NULL — never the JSON ``null`` (``IS NULL`` would not match it, the
trap ADR-322 measured on ``recurrence``) and never an empty list. The write is
strict against the account's REAL servers: its own enabled server is accepted,
another account's is refused and nothing is written.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import BaseAPIException
from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay
from src.domains.scheduled_actions.schemas import ScheduledActionCreate
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.user_mcp.models import UserMCPServer
from src.domains.users.models import User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_EVERY_DAY = RecurrenceSpec(
    freq="daily",
    times=DailyTimes(mode="at", at=(TimeOfDay(hour=8, minute=0),)),
    anchor_date=date(2026, 11, 2),
)


async def _account(session: AsyncSession) -> tuple[User, UUID]:
    user = User(email=f"preapproval_{uuid4().hex}@example.com", hashed_password="x", is_active=True)
    session.add(user)
    await session.flush()
    server = UserMCPServer(
        user_id=user.id, name="Notes", url="https://notes.example.com/mcp", status="active"
    )
    session.add(server)
    await session.flush()
    return user, server.id


async def _is_null(session: AsyncSession, action_id: UUID) -> bool:
    found = await session.execute(
        text(
            "SELECT mcp_preapproved_servers IS NULL FROM scheduled_actions WHERE id = :id"
        ).bindparams(id=action_id)
    )
    return bool(found.scalar_one())


async def test_a_routine_without_preapproval_stores_sql_null(async_session: AsyncSession) -> None:
    user, _server = await _account(async_session)
    service = ScheduledActionService(async_session)

    action = await service.create(
        user.id,
        ScheduledActionCreate(title="Tidy", action_prompt="tidy", recurrence=_EVERY_DAY),
        user_timezone="Europe/Paris",
    )
    await async_session.commit()

    assert await _is_null(async_session, action.id)
    assert action.mcp_preapproval is None


async def test_the_owners_server_is_kept_then_cleared_back_to_null(
    async_session: AsyncSession,
) -> None:
    user, server_id = await _account(async_session)
    service = ScheduledActionService(async_session)
    action = await service.create(
        user.id,
        ScheduledActionCreate(title="Tidy", action_prompt="tidy", recurrence=_EVERY_DAY),
        user_timezone="Europe/Paris",
    )

    await service.set_mcp_preapproval(action, user, [str(server_id)])
    await async_session.commit()
    await async_session.refresh(action)
    kept = action.mcp_preapproved_servers

    await service.set_mcp_preapproval(action, user, [])
    await async_session.commit()

    assert kept == [str(server_id)]
    assert await _is_null(async_session, action.id), "cleared is SQL NULL, never []"


async def test_another_accounts_server_is_refused_and_nothing_written(
    async_session: AsyncSession,
) -> None:
    user, _mine = await _account(async_session)
    _other, theirs = await _account(async_session)
    service = ScheduledActionService(async_session)
    action = await service.create(
        user.id,
        ScheduledActionCreate(title="Tidy", action_prompt="tidy", recurrence=_EVERY_DAY),
        user_timezone="Europe/Paris",
    )
    await async_session.commit()

    with pytest.raises(BaseAPIException) as refused:
        await service.set_mcp_preapproval(action, user, [str(theirs)])

    assert refused.value.detail == {
        "code": "routine_mcp_server_not_callable",
        "servers": [str(theirs)],
    }
    assert await _is_null(async_session, action.id)
