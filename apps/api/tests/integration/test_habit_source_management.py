"""The shared source UI command remains available when native/learning switches are off."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundError
from src.domains.habits.management_commands import managed_habit
from src.domains.habits.models import UserHabit
from src.domains.habits.router import delete_habit, set_habit_status
from src.domains.habits.schemas import HabitStatusUpdate
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("operation", ["status", "delete", "foreign"])
async def test_source_control_does_not_depend_on_native_tools(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", False)
    row = UserHabit(
        user_id=test_user.id,
        kind="recurring_request",
        key="email",
        status="active",
        payload={"version": 1},
        last_observed_at=datetime.now(UTC),
    )
    async_session.add(row)
    await async_session.commit()
    identity = row.id
    if operation == "foreign":
        other = User(
            id=uuid4(),
            email=f"habit-foreign-{uuid4()}@example.test",
            full_name="Other",
            is_active=True,
            is_verified=True,
        )
        async_session.add(other)
        await async_session.commit()
        with pytest.raises(ResourceNotFoundError):
            await set_habit_status(
                identity, HabitStatusUpdate(status="blocked"), other, async_session
            )
        with pytest.raises(ResourceNotFoundError):
            await delete_habit(identity, other, async_session)
        kept = await managed_habit(async_session, test_user.id, identity)
        assert kept.status.value == "active"
    elif operation == "delete":
        await delete_habit(identity, test_user, async_session)
        with pytest.raises(ResourceNotFoundError):
            await managed_habit(async_session, test_user.id, identity)
    else:
        result = await set_habit_status(
            identity, HabitStatusUpdate(status="blocked"), test_user, async_session
        )
        assert result.status.value == "blocked" and result.payload == {"version": 1}
        assert (
            await managed_habit(async_session, test_user.id, identity)
        ).status.value == "blocked"
