"""Only the sealed current owned habit may change after exact approval."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.habit_action_schemas import (
    HabitDeleteRequest,
    HabitStatusRequest,
)
from src.domains.agents.application.habit_actions import execute_habit_action, prepare_habit_action
from src.domains.habits.models import UserHabit
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "paused",
        "active",
        "blocked",
        "no_op",
        "stale",
        "foreign",
        "missing",
        "expired",
        "withdrawn",
        "late_withdrawn",
        "unknown",
        "unknown_committed",
        "delete",
    ],
)
async def test_exact_habit_management(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    monkeypatch.setattr(settings, "habits_enabled", True)
    row = UserHabit(
        user_id=test_user.id,
        kind="recurring_request",
        key="email",
        status="paused" if scenario == "active" else "active",
        payload={"version": 1},
        last_observed_at=datetime.now(UTC),
    )
    async_session.add(row)
    await async_session.commit()
    owner, habit_id = test_user.id, row.id
    desired = scenario if scenario in {"active", "paused", "blocked"} else "paused"
    if scenario == "no_op":
        desired = "active"
    request = (
        HabitDeleteRequest(habit_id=habit_id)
        if scenario == "delete"
        else HabitStatusRequest(habit_id=habit_id, status=desired)
    )
    draft = await prepare_habit_action(async_session, owner, request)
    if scenario in {"stale", "foreign", "missing"}:
        if scenario == "missing":
            await async_session.delete(row)
        elif scenario == "foreign":
            # A different identity is indistinguishable from an unowned record.
            draft = draft.model_copy(update={"actor_id": __import__("uuid").uuid4()})
        else:
            await async_session.execute(
                update(UserHabit).where(UserHabit.id == habit_id).values(payload={"version": 2})
            )
        await async_session.commit()
    if scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    if scenario == "withdrawn":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    if scenario == "late_withdrawn":
        original_flush = async_session.flush

        async def withdraw(*args, **kwargs):
            await original_flush(*args, **kwargs)
            monkeypatch.setattr(settings, "application_tools_enabled", False)

        monkeypatch.setattr(async_session, "flush", withdraw)
    receipt = PreferenceWriteReceipt()
    if scenario in {"stale", "missing", "foreign", "expired", "withdrawn", "late_withdrawn"}:
        with pytest.raises(
            (ResourceConflictError, ResourceNotFoundError, AuthorizationError, CommandRejected)
        ):
            await execute_habit_action(async_session, owner, draft, receipt)
        await async_session.rollback()
        assert not receipt.committed
        return
    if scenario.startswith("unknown"):
        original_commit = async_session.commit

        async def lose_ack():
            if scenario == "unknown_committed":
                await original_commit()
            raise SQLAlchemyError("lost acknowledgement")

        with patch.object(async_session, "commit", side_effect=lose_ack):
            with pytest.raises(CommandRejected, match="COMPLETION_UNKNOWN"):
                await execute_habit_action(async_session, owner, draft, receipt)
        await async_session.rollback()
        assert not receipt.committed
        await async_session.refresh(row)
        assert row.status == (desired if scenario == "unknown_committed" else "active")
        return
    await execute_habit_action(async_session, owner, draft, receipt)
    assert receipt.committed and receipt.no_op is (scenario == "no_op")
    if scenario == "delete":
        from src.domains.habits.repository import HabitsRepository

        assert await HabitsRepository(async_session).get_owned(habit_id, owner) is None
    else:
        await async_session.refresh(row)
        assert row.status == desired and row.payload == {"version": 1}
