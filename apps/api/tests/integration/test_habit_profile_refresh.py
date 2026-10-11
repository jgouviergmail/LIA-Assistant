"""Raw SQL profile upserts must be observed even with an older ORM instance loaded."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.habits.models import UserHabitProfile
from src.domains.habits.repository import HabitsRepository
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_profile_reader_observes_the_current_persisted_compute(
    async_session: AsyncSession, test_user: User
) -> None:
    old = datetime.now(UTC) - timedelta(days=1)
    row = UserHabitProfile(user_id=test_user.id, payload={"version": 1}, computed_at=old)
    async_session.add(row)
    await async_session.flush()
    current = datetime.now(UTC)
    await HabitsRepository(async_session).upsert_profile(
        test_user.id, {"version": 2}, current, None
    )
    result = await HabitsRepository(async_session).get_profile(test_user.id)
    assert result.computed_at == current and result.payload == {"version": 2}
