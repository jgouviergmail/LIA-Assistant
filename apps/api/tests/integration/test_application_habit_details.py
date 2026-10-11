"""The native explanation uses the same owned detector evidence and thresholds as the UI."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundError
from src.domains.agents.application.habit_detail_schemas import HabitDetailRead
from src.domains.agents.application.habit_details import read_habit_details
from src.domains.habits.models import UserHabit
from src.domains.habits.service import HabitsService
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["window", "recurrence", "missing", "foreign", "raw_tool"])
async def test_habit_details_keep_current_owned_source_evidence_and_real_dates(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "habits_enabled", True)
    row = UserHabit(
        user_id=test_user.id,
        kind="active_window" if scenario == "window" else "recurring_request",
        key="source-key",
        payload={"version": 1, "offer_dates": ["2026-10-01"]},
        status="blocked",
        last_observed_at=datetime.now(UTC),
    )
    async_session.add(row)
    await async_session.commit()
    dates = AsyncMock(return_value=["2026-10-07", "2026-10-06"])
    monkeypatch.setattr(
        "src.domains.habits.management_explanation.observed_days_for_signature", dates
    )
    request = HabitDetailRead(habit_id=uuid4() if scenario == "missing" else row.id)
    if scenario == "foreign":
        other = User(
            id=uuid4(),
            email=f"habit-detail-other-{uuid4()}@example.test",
            full_name="Other",
            is_active=True,
            is_verified=True,
        )
        async_session.add(other)
        await async_session.commit()
        with pytest.raises(ResourceNotFoundError):
            await read_habit_details(async_session, other.id, request)
        dates.assert_not_called()
        return
    if scenario == "missing":
        with pytest.raises(ResourceNotFoundError):
            await read_habit_details(async_session, test_user.id, request)
        dates.assert_not_called()
        return
    result = await read_habit_details(async_session, test_user.id, request)
    if scenario == "raw_tool":
        from contextlib import asynccontextmanager

        from langgraph.store.memory import InMemoryStore

        from src.domains.agents.tools import application_habit_tools
        from tests.helpers.runtime_context import make_tool_runtime

        @asynccontextmanager
        async def session():
            yield async_session

        monkeypatch.setattr(application_habit_tools, "get_db_context", session)
        output = await application_habit_tools.get_lia_habit_details_tool.coroutine(
            query={"habit_id": str(row.id)},
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore()),
        )
        assert output.success and output.structured_data["habit_id"] == str(row.id)
        assert not output.registry_updates and not output.metadata.get("requires_confirmation")
        return
    source = HabitsService(async_session).build_explanation(row)
    for name, value in source.items():
        assert getattr(result, name) == value
    assert result.observed_days == ([] if scenario == "window" else ["2026-10-07", "2026-10-06"])
    assert result.habit_id == row.id and row.status == "blocked"
    if scenario == "window":
        dates.assert_not_called()
    else:
        dates.assert_awaited_once_with(test_user.id, row.key)
