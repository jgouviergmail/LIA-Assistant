"""Pausing, blocking or deleting a learned window stops its consumption —
on a real PostgreSQL, through the real nightly sync and the three real
consumers (ADR-214 decision 3, measured violated 2026-09-11 — sim H).

The replay of the measurement: 42 days of afternoon presence, one nightly
recompute, then the person refuses the windows the panel shows. Every
consumer must go quiet, and the nightly resync must not resurrect a blocked
window (the tombstone), while a deleted row IS relearned (the documented
contract: « it may be relearned unless blocked first »).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings as app_settings
from src.domains.habits.consumption import load_consumable_profile
from src.domains.habits.models import HabitKind, HabitStatus, UserHabit
from src.domains.habits.repository import HabitsRepository
from src.domains.habits.service import HabitsService
from src.domains.heartbeat.habit_context import fetch_habits_context
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def owner(async_session: AsyncSession) -> User:
    user = User(
        email=f"habits-status-{uuid.uuid4().hex[:10]}@example.com",
        hashed_password="x",
        full_name="Habits Status Owner",
        is_active=True,
        is_verified=True,
    )
    user.timezone = "Europe/Paris"
    user.habits_enabled = True
    async_session.add(user)
    await async_session.flush()
    return user


async def _learn_afternoons(session: AsyncSession, user: User) -> None:
    today = datetime.now(UTC).date()
    days: dict[date, dict[int, int]] = {}
    for k in range(1, 43):
        days[today - timedelta(days=k)] = {14: 2, 15: 1}
    await HabitsRepository(session).upsert_activity_days(user.id, days)
    await session.flush()
    outcome = await HabitsService(session).recompute_user_profile(user, force=True)
    assert outcome == "computed"
    await session.flush()


async def _window_rows(session: AsyncSession, user_id: uuid.UUID) -> list[UserHabit]:
    result = await session.execute(
        select(UserHabit).where(
            UserHabit.user_id == user_id, UserHabit.kind == HabitKind.ACTIVE_WINDOW.value
        )
    )
    return list(result.scalars().all())


async def test_learned_windows_are_consumable_while_active(
    async_session: AsyncSession, owner: User
) -> None:
    await _learn_afternoons(async_session, owner)
    rows = await _window_rows(async_session, owner.id)
    assert {r.key for r in rows} == {"weekday:afternoon", "weekend:afternoon"}

    profile = await load_consumable_profile(HabitsRepository(async_session), owner.id)
    assert profile is not None and profile.weekday.windows and profile.weekend.windows
    block = await fetch_habits_context(async_session, owner.id, owner, app_settings)
    assert block is not None and block["rhythm"] is not None


@pytest.mark.parametrize("status", [HabitStatus.BLOCKED.value, HabitStatus.PAUSED.value])
async def test_refusing_the_windows_silences_every_consumer(
    async_session: AsyncSession, owner: User, status: str
) -> None:
    await _learn_afternoons(async_session, owner)
    repo = HabitsRepository(async_session)
    for row in await _window_rows(async_session, owner.id):
        await repo.set_status(row, status)
    await async_session.flush()

    # 1. the consumption predicate
    profile = await load_consumable_profile(repo, owner.id)
    assert profile is not None
    assert profile.weekday.windows == () and profile.weekend.windows == ()
    # the detector's own truth stays visible to the panel
    assert profile.weekday.verdict == "windows"

    # 2. the heartbeat block (rhythm part)
    block = await fetch_habits_context(async_session, owner.id, owner, app_settings)
    assert block is None

    # (The ambient block opens its own session and cannot see this test's
    # transaction; its reading of the same predicate is pinned in
    # tests/unit/domains/habits/test_ambient_block.py.)

    # 3. the nightly resync keeps the person's decision (no reactivation)
    await HabitsService(async_session).recompute_user_profile(owner, force=True)
    await async_session.flush()
    assert {r.status for r in await _window_rows(async_session, owner.id)} == {status}


async def test_a_deleted_window_is_quiet_until_the_nightly_relearns_it(
    async_session: AsyncSession, owner: User
) -> None:
    await _learn_afternoons(async_session, owner)
    repo = HabitsRepository(async_session)
    for row in await _window_rows(async_session, owner.id):
        await repo.delete_habit(row)
    await async_session.flush()

    profile = await load_consumable_profile(repo, owner.id)
    assert profile is not None and profile.weekday.windows == ()
    assert await fetch_habits_context(async_session, owner.id, owner, app_settings) is None

    # The documented contract: deleted (not blocked) rows come back at the
    # next nightly sync, and with them the consumption.
    await HabitsService(async_session).recompute_user_profile(owner, force=True)
    await async_session.flush()
    rows = await _window_rows(async_session, owner.id)
    assert {r.status for r in rows} == {HabitStatus.ACTIVE.value}
    profile = await load_consumable_profile(repo, owner.id)
    assert profile is not None and profile.weekday.windows


async def test_the_key_the_sync_writes_is_the_key_the_predicate_reads(
    async_session: AsyncSession, owner: User
) -> None:
    """One producer of the window key (``window_keys``): the rows the sync
    wrote must unlock exactly the profile's windows — a second wording of
    the key on either side would leave every window unconsumable."""
    await _learn_afternoons(async_session, owner)
    repo = HabitsRepository(async_session)
    stored = await repo.get_profile(owner.id)
    assert stored is not None
    consumable = await load_consumable_profile(repo, owner.id)
    assert consumable is not None
    from src.domains.habits.rhythm import RhythmProfile

    assert consumable == RhythmProfile.from_payload(stored.payload)
