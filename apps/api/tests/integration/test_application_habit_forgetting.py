"""Complete owned forgetting reports cross-store failure without inventing full success."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.habit_forget_schemas import HabitForgetRequest
from src.domains.agents.application.habit_forgetting import (
    execute_habit_forgetting,
    prepare_habit_forgetting,
)
from src.domains.habits.models import UserActivityDay, UserHabit, UserHabitProfile
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    ["complete", "stale", "redis_down", "new_row", "late_off", "unknown", "unknown_committed"],
)
async def test_full_habit_forgetting_is_complete_owned_and_honest(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    monkeypatch.setattr(settings, "habits_enabled", True)
    owner = test_user.id
    foreign = User(
        id=uuid4(),
        email=f"habit-erase-other-{uuid4()}@example.test",
        full_name="Other",
        is_active=True,
        is_verified=True,
    )
    async_session.add(foreign)
    await async_session.flush()
    foreign_habit = UserHabit(
        user_id=foreign.id,
        kind="recurring_request",
        key="private-foreign",
        status="blocked",
        payload={},
        last_observed_at=datetime.now(UTC),
    )
    async_session.add(foreign_habit)
    async_session.add_all(
        [
            UserHabit(
                user_id=owner,
                kind="recurring_request",
                key=f"habit-{index:03}",
                status=("blocked" if index % 2 else "paused"),
                payload={"version": 1},
                last_observed_at=datetime.now(UTC),
            )
            for index in range(203)
        ]
    )
    async_session.add(
        UserHabitProfile(
            user_id=owner, payload={"private": "rhythm"}, computed_at=datetime.now(UTC)
        )
    )
    async_session.add(UserActivityDay(user_id=owner, local_date=date.today(), hour_counts={"9": 2}))
    await async_session.commit()
    draft = await prepare_habit_forgetting(
        async_session, owner, HabitForgetRequest(scope="all_owned")
    )
    assert "rhythm" not in str(draft.before) and "habit-" not in str(draft.before)
    cleanup = AsyncMock(return_value=True)
    if scenario == "redis_down":
        cleanup.return_value = False
    monkeypatch.setattr("src.domains.habits.forgetting.clear_habit_advisory_state", cleanup)
    if scenario == "stale":
        await async_session.execute(
            update(UserHabitProfile)
            .where(UserHabitProfile.user_id == owner)
            .values(payload={"private": "changed"})
        )
        await async_session.commit()
    if scenario == "new_row":
        async_session.add(
            UserHabit(
                user_id=owner,
                kind="recurring_request",
                key="new",
                status="active",
                payload={},
                last_observed_at=datetime.now(UTC),
            )
        )
        await async_session.commit()
    receipt = PreferenceWriteReceipt()
    if scenario.startswith("unknown"):
        original_commit = async_session.commit

        async def lose_ack():
            if scenario == "unknown_committed":
                await original_commit()
            raise SQLAlchemyError("lost acknowledgement")

        with patch.object(async_session, "commit", side_effect=lose_ack):
            with pytest.raises(CommandRejected, match="COMPLETION_UNKNOWN"):
                await execute_habit_forgetting(async_session, owner, draft, receipt)
        await async_session.rollback()
        assert not receipt.committed and receipt.values is None
        cleanup.assert_not_awaited()
        kept = await async_session.scalar(select(UserHabit.id).where(UserHabit.user_id == owner))
        assert (kept is None) is (scenario == "unknown_committed")
        return
    if scenario == "late_off":
        original_commit = async_session.commit

        async def withdraw_after_commit():
            await original_commit()
            monkeypatch.setattr(settings, "application_tools_enabled", False)

        monkeypatch.setattr(async_session, "commit", withdraw_after_commit)
        with pytest.raises(AuthorizationError):
            await execute_habit_forgetting(async_session, owner, draft, receipt)
        assert receipt.committed and not receipt.values["advisory_cleanup_confirmed"]
        cleanup.assert_not_awaited()
        assert (
            await async_session.scalar(select(UserHabit.id).where(UserHabit.user_id == owner))
            is None
        )
        return
    if scenario in {"stale", "new_row"}:
        with pytest.raises(ResourceConflictError):
            await execute_habit_forgetting(async_session, owner, draft, receipt)
        await async_session.rollback()
        assert not receipt.committed
        cleanup.assert_not_awaited()
        return
    if scenario == "redis_down":
        with pytest.raises(CommandRejected, match="ADVISORY_CLEANUP_FAILED"):
            await execute_habit_forgetting(async_session, owner, draft, receipt)
    else:
        await execute_habit_forgetting(async_session, owner, draft, receipt)
    assert receipt.committed and receipt.values == {
        "deleted_habits": 203,
        "profile_deleted": True,
        "deleted_activity_days": 1,
        "advisory_cleanup_confirmed": scenario != "redis_down",
    }
    assert (
        await async_session.scalar(select(UserHabit.id).where(UserHabit.user_id == owner)) is None
    )
    assert (
        await async_session.scalar(
            select(UserHabitProfile.id).where(UserHabitProfile.user_id == owner)
        )
        is None
    )
    assert (
        await async_session.scalar(
            select(UserActivityDay.id).where(UserActivityDay.user_id == owner)
        )
        is None
    )
    cleanup.assert_awaited_once_with(owner)
    assert (
        await async_session.scalar(select(UserHabit.id).where(UserHabit.user_id == foreign.id))
        == foreign_habit.id
    )
