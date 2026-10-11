"""A detector's stale observation cannot undo the owner's pause or block."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.habits.models import UserHabit
from src.domains.habits.recurrence_sync import _demote_if_active, _PassState
from src.domains.habits.repository import HabitsRepository
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "action", ["refresh_blocked", "demote_paused", "demote_blocked", "touch_blocked"]
)
async def test_stale_detector_preserves_user_control(
    async_session: AsyncSession, test_user: User, action: str
) -> None:
    row = UserHabit(
        user_id=test_user.id,
        kind="recurring_request",
        key="email",
        payload={"version": 1, "offer_dates": ["2026-10-01"]},
        status="active",
        last_observed_at=datetime.now(UTC),
    )
    async_session.add(row)
    await async_session.flush()
    status = "paused" if action == "demote_paused" else "blocked"
    await async_session.execute(
        update(UserHabit).where(UserHabit.id == row.id).values(status=status),
        execution_options={"synchronize_session": False},
    )
    assert row.status == "active"  # The detector really carries an older ORM observation.
    repo = HabitsRepository(async_session)
    state = _PassState(rows={}, slots_used=1, cap=settings.habits_max_habits_per_kind)
    observed_before = row.last_observed_at
    if action == "touch_blocked":
        await repo.touch_habit(row, datetime.now(UTC))
    elif action == "refresh_blocked":
        outcome = await repo.upsert_habit(
            test_user.id, row.kind, row.key, {"version": 2}, datetime.now(UTC)
        )
        assert outcome == "blocked"
    else:
        await _demote_if_active(repo, row, state)
        assert state.slots_used == 1 and state.counts == {}
    await async_session.flush()
    kept = await repo.get_owned(row.id, test_user.id)
    assert kept is not None and kept.status == status
    assert kept.payload == {"version": 1, "offer_dates": ["2026-10-01"]}
    assert kept.last_observed_at == observed_before
