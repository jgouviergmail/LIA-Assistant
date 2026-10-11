"""Habit learning preference changes are exact and revocable without deleting retained records."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application import habit_settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.habit_settings_schemas import HabitSettingsPatch
from src.domains.habits.models import UserHabit
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    ["disable", "enable", "no_op", "stale", "late_disabled", "unknown", "unknown_committed", "ui"],
)
async def test_confirmed_habit_preference_matches_source_and_preserves_records(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "habits_enabled", True)
    owner = test_user.id
    initial = scenario != "enable"
    await async_session.execute(update(User).where(User.id == owner).values(habits_enabled=initial))
    row = UserHabit(
        user_id=owner,
        kind="recurring_request",
        key="retained",
        payload={"version": 1},
        status="blocked",
        last_observed_at=datetime.now(UTC),
    )
    async_session.add(row)
    await async_session.commit()
    desired = scenario in {"enable", "no_op"}
    draft = await habit_settings.prepare_habit_settings(
        async_session, owner, HabitSettingsPatch(habits_enabled=desired)
    )
    if scenario == "stale":
        await async_session.execute(
            update(User).where(User.id == owner).values(habits_enabled=not initial)
        )
        await async_session.commit()
    if scenario == "late_disabled":
        original_flush = async_session.flush

        async def withdraw(*args, **kwargs):
            await original_flush(*args, **kwargs)
            monkeypatch.setattr(settings, "application_tools_enabled", False)

        monkeypatch.setattr(async_session, "flush", withdraw)
    receipt = PreferenceWriteReceipt()
    if scenario == "ui":
        from src.domains.habits.router import update_habits_settings
        from src.domains.habits.schemas import HabitsSettingsUpdate

        monkeypatch.setattr(settings, "application_tools_enabled", False)
        result = await update_habits_settings(
            HabitsSettingsUpdate(habits_enabled=False), test_user, async_session
        )
        await async_session.refresh(test_user)
        await async_session.refresh(row)
        assert (
            not result.habits_enabled and not test_user.habits_enabled and row.status == "blocked"
        )
        return
    if scenario in {"stale", "late_disabled"}:
        with pytest.raises(ResourceConflictError if scenario == "stale" else AuthorizationError):
            await habit_settings.execute_habit_settings(async_session, owner, draft, receipt)
        await async_session.rollback()
        assert not receipt.committed
        return
    if scenario in {"unknown", "unknown_committed"}:
        original_commit = async_session.commit

        async def lose_ack() -> None:
            if scenario == "unknown_committed":
                await original_commit()
            raise SQLAlchemyError("ack lost")

        with patch.object(async_session, "commit", side_effect=lose_ack):
            with pytest.raises(CommandRejected, match="COMPLETION_UNKNOWN"):
                await habit_settings.execute_habit_settings(async_session, owner, draft, receipt)
        await async_session.rollback()
        assert not receipt.committed
        if scenario == "unknown_committed":
            await async_session.refresh(test_user)
            assert test_user.habits_enabled is desired
        return
    await habit_settings.execute_habit_settings(async_session, owner, draft, receipt)
    await async_session.refresh(test_user)
    await async_session.refresh(row)
    assert receipt.committed and receipt.no_op is (scenario == "no_op")
    assert test_user.habits_enabled is desired
    assert row.status == "blocked" and row.payload == {"version": 1}
