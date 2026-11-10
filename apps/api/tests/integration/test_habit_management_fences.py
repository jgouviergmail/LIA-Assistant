"""A detector's stale observation cannot undo the owner's pause or block (ADR-375)."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.habits.models import UserHabit
from src.domains.habits.recurrence_sync import sync_recurring_habits
from src.domains.habits.repository import HabitsRepository
from src.domains.habits.usage_observations import LedgerView
from src.domains.users.models import User

pytestmark = pytest.mark.integration

PAYLOAD = {"version": 2, "domain": "email", "cadence": "daily", "part_of_day": "morning"}


@pytest.mark.parametrize("action", ["refresh_blocked", "demote_paused", "demote_blocked"])
async def test_stale_detector_preserves_user_control(
    async_session: AsyncSession, test_user: User, action: str
) -> None:
    row = UserHabit(
        user_id=test_user.id,
        kind="recurring_request",
        key="email",
        payload=dict(PAYLOAD),
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
    observed_before = row.last_observed_at
    if action == "refresh_blocked":
        outcome = await repo.upsert_habit(
            test_user.id, row.kind, row.key, {**PAYLOAD, "distinct_days": 9}, datetime.now(UTC)
        )
        assert outcome == "blocked"
    else:
        # The need lapsed tonight: only a STILL-active row may be demoted.
        synced = await sync_recurring_habits(
            repo,
            test_user.id,
            (),
            LedgerView(readable=True, days_by_domain={}, intents={}),
            tz=ZoneInfo("UTC"),
            settings=settings,
        )
        assert synced.demoted == 0
    await async_session.flush()
    kept = await repo.get_owned(row.id, test_user.id)
    assert kept is not None and kept.status == status
    assert kept.payload == PAYLOAD
    assert kept.last_observed_at == observed_before
