"""The recurring habit's life, on a real PostgreSQL, through the real nightly
recompute (ADR-214 amendment c). Replays the 2026-09-11 measurements:

- sim B: two ignored offers muted the habit and a live occurrence the next
  day did NOT lift the mute (it waited for the next chat fire, ≥ 30 days);
- sim C4-b: a promoted habit whose ledger had EXPIRED was still offered as a
  « missed routine » — a ghost;
- sim C15: the promotion itself depended on the chat suggestion firing.

The ledger is the NX-faithful in-memory double the seed tests use (advisory
Redis); the rows, the statuses and the recompute are real.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings as app_settings
from src.domains.habits.models import HabitKind, HabitStatus, UserHabit
from src.domains.habits.recurrence_sync import sync_recurring_habits
from src.domains.habits.repository import HabitsRepository
from src.domains.habits.service import HabitsService
from src.domains.heartbeat.habit_context import fetch_habits_context
from src.domains.heartbeat.proactive_task import _bump_offered_habit
from src.domains.users.models import User
from src.infrastructure.cache import recurrence_store

pytestmark = pytest.mark.integration

TZ = ZoneInfo("Europe/Paris")


class _FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> Any:
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def delete(self, *keys: str) -> int:
        return sum(1 for k in keys if self.data.pop(k, None) is not None)

    async def ttl(self, key: str) -> int:
        return 3600

    def scan_iter(self, match: str) -> Any:
        prefix = match[:-1]

        async def _iter() -> Any:
            for key in list(self.data):
                if key.startswith(prefix):
                    yield key

        return _iter()


@pytest_asyncio.fixture
async def owner(async_session: AsyncSession) -> User:
    user = User(
        email=f"habits-sync-{uuid.uuid4().hex[:10]}@example.com",
        hashed_password="x",
        full_name="Habits Sync Owner",
        is_active=True,
        is_verified=True,
    )
    user.timezone = "Europe/Paris"
    user.language = "fr"
    user.habits_enabled = True
    async_session.add(user)
    await async_session.flush()
    return user


def _ledger(
    redis: _FakeRedis, user_id: uuid.UUID, signature: str, days: dict[date, list[float]]
) -> None:
    payload = {
        "days": {d.isoformat(): h for d, h in days.items()},
        "suggested_at": None,
        "origin": "live",
    }
    redis.data[recurrence_store.redis_key(str(user_id), signature)] = json.dumps(payload)


def _daily(today: date, *, first: int, last: int, hour: float = 9.0) -> dict[date, list[float]]:
    return {today - timedelta(days=k): [hour] for k in range(first, last + 1)}


async def _rows(session: AsyncSession, user_id: uuid.UUID) -> list[UserHabit]:
    result = await session.execute(
        select(UserHabit).where(
            UserHabit.user_id == user_id, UserHabit.kind == HabitKind.RECURRING_REQUEST.value
        )
    )
    return list(result.scalars().all())


def _patch(redis: _FakeRedis) -> Any:
    return patch("src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=redis))


async def test_the_nightly_recompute_promotes_a_locked_signature_without_a_chat_turn(
    async_session: AsyncSession, owner: User
) -> None:
    redis = _FakeRedis()
    today = datetime.now(TZ).date()
    _ledger(redis, owner.id, "email", _daily(today, first=1, last=21))
    # The recompute short-circuits an account with no activity at all before
    # it reaches the ledger; a person with a ledger has typed, so give the
    # rollup the days those turns banked.
    await HabitsRepository(async_session).upsert_activity_days(
        owner.id, {today - timedelta(days=k): {9: 1} for k in range(1, 22)}
    )
    await async_session.flush()
    with _patch(redis):
        await HabitsService(async_session).recompute_user_profile(owner, force=True)
    await async_session.flush()
    [row] = await _rows(async_session, owner.id)
    assert row.key == "email" and row.status == HabitStatus.ACTIVE.value
    assert row.payload["shape"] == "daily" and row.payload["version"] == 1
    assert row.last_observed_at.astimezone(TZ).date() == today - timedelta(days=1)


async def test_mute_lifts_on_a_fresh_occurrence_and_offer_dates_survive(
    async_session: AsyncSession, owner: User
) -> None:
    redis = _FakeRedis()
    today = datetime.now(TZ).date()
    # occurrences stopped 10 days ago → the slot is missed today (k=2 rule)
    _ledger(redis, owner.id, "email", _daily(today, first=10, last=30))
    repo = HabitsRepository(async_session)
    with _patch(redis):
        await sync_recurring_habits(repo, owner.id, "Europe/Paris", app_settings)
        await async_session.flush()
        [row] = await _rows(async_session, owner.id)
        # two offers → muted (the stop rule)
        row.payload = {**row.payload, "offer_dates": [(today - timedelta(days=9)).isoformat()]}
        await async_session.flush()
        await _bump_offered_habit(async_session, owner.id, {"habit_offer_id": str(row.id)})
        await async_session.flush()
        assert row.muted_until_reproof is True
        offers_before = list(row.payload["offer_dates"])
        assert await fetch_habits_context(async_session, owner.id, owner, app_settings) is None

        # the routine re-occurs → the next nightly lifts the mute, keeps the bookkeeping
        _ledger(redis, owner.id, "email", {**_daily(today, first=10, last=30), today: [9.1]})
        await sync_recurring_habits(repo, owner.id, "Europe/Paris", app_settings)
        await async_session.flush()
        await async_session.refresh(row)
        assert row.muted_until_reproof is False
        assert row.payload["offer_dates"] == offers_before
        assert row.payload["shape"] == "daily"


async def test_an_expired_ledger_demotes_the_ghost_routine(
    async_session: AsyncSession, owner: User
) -> None:
    redis = _FakeRedis()
    today = datetime.now(TZ).date()
    _ledger(redis, owner.id, "email", _daily(today, first=1, last=21))
    repo = HabitsRepository(async_session)
    with _patch(redis):
        await sync_recurring_habits(repo, owner.id, "Europe/Paris", app_settings)
        await async_session.flush()
        assert len(await _rows(async_session, owner.id)) == 1
        # the ledger expires (35-day TTL): no key at all
        redis.data.clear()
        await sync_recurring_habits(repo, owner.id, "Europe/Paris", app_settings)
        await async_session.flush()
        assert await _rows(async_session, owner.id) == []
        # …and the heartbeat has nothing left to offer
        assert await fetch_habits_context(async_session, owner.id, owner, app_settings) is None


@pytest.mark.parametrize("status", [HabitStatus.PAUSED.value, HabitStatus.BLOCKED.value])
async def test_the_persons_own_statuses_survive_the_ledger(
    async_session: AsyncSession, owner: User, status: str
) -> None:
    redis = _FakeRedis()
    today = datetime.now(TZ).date()
    _ledger(redis, owner.id, "email", _daily(today, first=1, last=21))
    repo = HabitsRepository(async_session)
    with _patch(redis):
        await sync_recurring_habits(repo, owner.id, "Europe/Paris", app_settings)
        await async_session.flush()
        [row] = await _rows(async_session, owner.id)
        await repo.set_status(row, status)
        await async_session.flush()
        redis.data.clear()
        await sync_recurring_habits(repo, owner.id, "Europe/Paris", app_settings)
        await async_session.flush()
        [kept] = await _rows(async_session, owner.id)
        assert kept.id == row.id and kept.status == status
        # a blocked signature never comes back even when it locks again
        _ledger(redis, owner.id, "email", _daily(today, first=1, last=21))
        await sync_recurring_habits(repo, owner.id, "Europe/Paris", app_settings)
        await async_session.flush()
        [still] = await _rows(async_session, owner.id)
        assert still.id == row.id and still.status == status


async def test_redis_down_leaves_every_row_alone(async_session: AsyncSession, owner: User) -> None:
    repo = HabitsRepository(async_session)
    await repo.upsert_habit(
        user_id=owner.id,
        kind=HabitKind.RECURRING_REQUEST.value,
        key="email",
        payload={"version": 1, "shape": "daily"},
        last_observed_at=datetime.now(UTC),
    )
    await async_session.flush()
    with _patch(None):
        outcome = await sync_recurring_habits(repo, owner.id, "Europe/Paris", app_settings)
    assert outcome.skipped is True
    assert len(await _rows(async_session, owner.id)) == 1
