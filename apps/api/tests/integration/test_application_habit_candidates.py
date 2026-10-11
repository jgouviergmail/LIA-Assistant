"""A candidate must not resurrect a blocked habit hidden beyond the returned page."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application import habit_queries
from src.domains.agents.application.habit_read_schemas import HabitRead
from src.domains.habits.candidates import RecurrenceCandidate
from src.domains.habits.models import UserHabit
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_candidate_exclusion_contains_all_owned_statuses_beyond_the_page(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "habits_enabled", True)
    monkeypatch.setattr(settings, "recurrence_suggestion_enabled", True)
    for index in range(12):
        async_session.add(
            UserHabit(
                user_id=test_user.id,
                kind="recurring_request",
                key=f"saved-{index:02d}",
                payload={"version": 1},
                status="blocked" if index == 11 else "active",
                last_observed_at=datetime.now(UTC),
            )
        )
    await async_session.commit()
    source = AsyncMock(return_value=([RecurrenceCandidate("new-observation", 2, 4, "seed")], 3))
    monkeypatch.setattr(habit_queries, "list_recurrence_candidates", source)
    result = await habit_queries.read_habits(async_session, test_user.id, HabitRead(limit=1))
    assert len(result.habits) == 1 and result.total == 12
    assert source.await_args.kwargs["exclude_keys"] == {f"saved-{index:02d}" for index in range(12)}
    assert result.candidates_more == 3 and result.candidates[0].origin == "seed"
