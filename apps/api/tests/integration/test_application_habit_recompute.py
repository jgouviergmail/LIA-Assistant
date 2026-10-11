"""Manual recompute is an approved current-data action, with source results and fresh gates."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.habit_recompute import (
    execute_habit_recompute,
    prepare_habit_recompute,
)
from src.domains.agents.application.habit_recompute_schemas import HabitRecomputeRequest
from src.domains.habits.models import UserActivityDay
from src.domains.habits.repository import HabitsRepository
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "computed",
        "empty",
        "learning_off",
        "timezone_changed",
        "operator_off",
        "late_off",
        "unknown",
        "unknown_committed",
    ],
)
async def test_confirmed_recompute_uses_the_actual_source_pipeline(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    monkeypatch.setattr(settings, "habits_enabled", True)
    monkeypatch.setattr(
        "src.infrastructure.cache.redis.get_redis_cache",
        AsyncMock(side_effect=ConnectionError("advisory unavailable")),
    )
    owner = test_user.id
    test_user.timezone = "UTC"
    test_user.habits_enabled = scenario != "learning_off"
    if scenario != "empty":
        async_session.add_all(
            [
                UserActivityDay(
                    user_id=owner,
                    local_date=date.today() - timedelta(days=index),
                    hour_counts={"9": 1},
                )
                for index in range(1, 29)
            ]
        )
    await async_session.commit()
    draft = await prepare_habit_recompute(
        async_session, owner, HabitRecomputeRequest(scope="current_account")
    )
    if scenario == "timezone_changed":
        await async_session.execute(
            update(User).where(User.id == owner).values(timezone="Europe/Paris")
        )
        await async_session.commit()
    if scenario == "operator_off":
        monkeypatch.setattr(settings, "habits_enabled", False)
    receipt = PreferenceWriteReceipt()
    if scenario == "late_off":
        original_flush = async_session.flush

        async def withdraw(*args, **kwargs):
            await original_flush(*args, **kwargs)
            monkeypatch.setattr(settings, "application_tools_enabled", False)

        monkeypatch.setattr(async_session, "flush", withdraw)
        with pytest.raises(AuthorizationError):
            await execute_habit_recompute(async_session, owner, draft, receipt)
        await async_session.rollback()
        assert not receipt.committed and receipt.values is None
        assert await HabitsRepository(async_session).get_profile(owner) is None
        return
    if scenario.startswith("unknown"):
        original_commit = async_session.commit

        async def lose_ack():
            if scenario == "unknown_committed":
                await original_commit()
            raise SQLAlchemyError("lost acknowledgement")

        with patch.object(async_session, "commit", side_effect=lose_ack):
            with pytest.raises(CommandRejected, match="COMPLETION_UNKNOWN"):
                await execute_habit_recompute(async_session, owner, draft, receipt)
        await async_session.rollback()
        assert not receipt.committed and receipt.values is None
        assert (await HabitsRepository(async_session).get_profile(owner) is not None) is (
            scenario == "unknown_committed"
        )
        return
    if scenario in {"timezone_changed", "operator_off"}:
        with pytest.raises(
            ResourceConflictError if scenario == "timezone_changed" else AuthorizationError
        ):
            await execute_habit_recompute(async_session, owner, draft, receipt)
        assert not receipt.committed
        return
    await execute_habit_recompute(async_session, owner, draft, receipt)
    assert receipt.committed and receipt.values["outcome"] == (
        "skipped_no_activity" if scenario == "empty" else "computed"
    )
    profile = await HabitsRepository(async_session).get_profile(owner)
    assert (profile is None) is (scenario == "empty")
    assert receipt.values["profile"]["computed_at"] == (
        None if profile is None else profile.computed_at.isoformat().replace("+00:00", "Z")
    )
