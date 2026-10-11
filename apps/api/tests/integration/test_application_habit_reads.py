"""Stored habits remain consultable when learning is off, with bounded complete owned pages."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application.habit_queries import read_habits
from src.domains.agents.application.habit_read_schemas import HabitRead
from src.domains.habits.models import UserHabit, UserHabitProfile
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "complete",
        "empty",
        "foreign_cursor",
        "native_off",
        "learning_off",
        "operator_off",
        "late_native_off",
        "late_actor_off",
        "late_source_off",
    ],
)
async def test_habit_reader_preserves_source_profile_and_complete_owned_scope(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "habits_enabled", True)
    monkeypatch.setattr(settings, "recurrence_suggestion_enabled", False)
    owner = test_user.id
    test_user.habits_enabled = scenario != "learning_off"
    other = User(
        id=uuid4(),
        email=f"habit-reader-{uuid4()}@example.test",
        full_name="Other",
        is_active=True,
        is_verified=True,
    )
    async_session.add(other)
    await async_session.flush()
    count = 0 if scenario == "empty" else 103
    rows = [
        UserHabit(
            user_id=owner,
            kind="recurring_request",
            key=f"source-{index:04d}",
            payload={"version": 1, "user_request": f"Owned request {index}"},
            status=("active", "paused", "blocked")[index % 3],
            last_observed_at=datetime.now(UTC),
        )
        for index in range(count)
    ]
    foreign = UserHabit(
        user_id=other.id,
        kind="recurring_request",
        key="Foreign secret",
        payload={"user_request": "Private other account text"},
        status="active",
        last_observed_at=datetime.now(UTC),
    )
    async_session.add_all([*rows, foreign])
    if scenario == "operator_off":
        async_session.add(
            SystemSetting(key=SystemSettingKey.CAPABILITY_HABITS_ENABLED, value="false")
        )
    await async_session.commit()
    if scenario == "native_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    request = HabitRead(limit=5, after_id=foreign.id if scenario == "foreign_cursor" else None)
    if scenario.startswith("late_"):
        from src.domains.agents.application import habit_queries

        source = habit_queries.read_habit_page

        async def withdraw(*args, **kwargs):
            result = await source(*args, **kwargs)
            if scenario == "late_native_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            elif scenario == "late_source_off":
                monkeypatch.setattr(settings, "habits_enabled", False)
            else:
                from sqlalchemy import update

                await async_session.execute(
                    update(User).where(User.id == owner).values(is_active=False)
                )
            return result

        monkeypatch.setattr(habit_queries, "read_habit_page", withdraw)
        with pytest.raises(AuthorizationError):
            await read_habits(async_session, owner, request)
        return
    if scenario in {"native_off", "foreign_cursor"}:
        with pytest.raises(
            AuthorizationError if scenario == "native_off" else ResourceNotFoundError
        ):
            await read_habits(async_session, owner, request)
        return
    seen = []
    while True:
        page = await read_habits(async_session, owner, request)
        assert page.total == count and len(page.habits) <= 5
        assert page.habits_enabled is (scenario != "learning_off")
        assert page.profile.computed_at is None and page.streak.current == 0
        assert "Private other account text" not in str(page.model_dump())
        seen.extend(item.id for item in page.habits)
        if page.next_cursor is None:
            break
        request = request.model_copy(update={"after_id": page.next_cursor})
    assert len(seen) == len(set(seen)) == count
    assert (
        await async_session.scalar(
            select(func.count())
            .select_from(UserHabitProfile)
            .where(UserHabitProfile.user_id == owner)
        )
        == 0
    )
