"""Integration tests for the per-day rollup against a real PostgreSQL.

``HealthSampleRepository.fetch_daily_stats`` replaced a raw-sample fetch on the
baseline / variations / heartbeat paths. The unit nets prove the *consumers*
behave identically given a per-day series; they cannot prove that PostgreSQL
produces the same series the in-Python grouping does — that half needs a real
database, and it is the half where a silent divergence would poison every
baseline downstream.

What is pinned here:

- **Bit-exact equality** with :func:`daily_stats_from_samples` over a dataset
  built to break naive implementations: samples straddling UTC midnight, a day
  whose values do not divide evenly (repeating decimal average), a single-sample
  day, and zero values.
- **Session-timezone independence.** Day bucketing uses an explicit
  ``timezone('UTC', ...)``; a connection whose ``TimeZone`` is UTC+14 must yield
  exactly the same days. Without the explicit cast this is the bug that ships:
  green in CI (UTC), wrong in production.
- **Window bounds**: ``date_start >= from_ts`` inclusive, ``< to_ts`` exclusive.
- Ordering, and the empty-window contract.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.health_metrics.baseline import DailyStat, daily_stats_from_samples
from src.domains.health_metrics.models import HealthSample
from src.domains.health_metrics.repository import HealthSampleRepository
from src.domains.users.models import User

pytestmark = pytest.mark.integration

# Fixed anchor: a UTC midnight boundary is the interesting edge, so every
# timestamp below is expressed relative to one.
ANCHOR = datetime(2026, 5, 20, 0, 0, tzinfo=UTC)


def _sample(user_id, kind: str, start: datetime, value: int) -> HealthSample:
    return HealthSample(
        user_id=user_id,
        kind=kind,
        date_start=start,
        date_end=start + timedelta(minutes=1),
        value=value,
        source="test",
    )


async def _seed(session: AsyncSession, user: User) -> None:
    """Insert a dataset designed to break naive day bucketing."""
    rows = [
        # Straddling UTC midnight: 23:59 on 05-19 and 00:01 on 05-20 must land
        # in DIFFERENT days. Under a UTC+14 session clock a naive cast would
        # merge them into 05-20.
        _sample(user.id, "heart_rate", ANCHOR - timedelta(minutes=1), 60),
        _sample(user.id, "heart_rate", ANCHOR + timedelta(minutes=1), 80),
        _sample(user.id, "heart_rate", ANCHOR + timedelta(minutes=2), 81),
        # 05-21: three values summing to 214 -> 71.333... (non-terminating)
        _sample(user.id, "heart_rate", ANCHOR + timedelta(days=1, hours=8), 70),
        _sample(user.id, "heart_rate", ANCHOR + timedelta(days=1, hours=9), 71),
        _sample(user.id, "heart_rate", ANCHOR + timedelta(days=1, hours=10), 73),
        # 05-22: single sample
        _sample(user.id, "heart_rate", ANCHOR + timedelta(days=2, hours=12), 65),
        # steps, including a zero-valued day (inactivity signal)
        _sample(user.id, "steps", ANCHOR + timedelta(hours=10), 4000),
        _sample(user.id, "steps", ANCHOR + timedelta(hours=11), 1500),
        _sample(user.id, "steps", ANCHOR + timedelta(days=1, hours=10), 0),
    ]
    session.add_all(rows)
    await session.commit()


async def _both_paths(
    session: AsyncSession, user: User, kind: str, from_ts: datetime, to_ts: datetime
) -> tuple[list[DailyStat], list[DailyStat]]:
    """Return (SQL rollup, in-Python grouping) over the same window."""
    repo = HealthSampleRepository(session)
    sql_side = await repo.fetch_daily_stats(user.id, kind=kind, from_ts=from_ts, to_ts=to_ts)
    samples = await repo.fetch_samples_kind(user.id, kind=kind, from_ts=from_ts, to_ts=to_ts)
    return sql_side, daily_stats_from_samples(samples)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["heart_rate", "steps"])
async def test_rollup_matches_in_python_grouping(
    async_session: AsyncSession, test_user: User, kind: str
) -> None:
    """The SQL rollup must equal the in-Python grouping, field for field."""
    await _seed(async_session, test_user)

    sql_side, python_side = await _both_paths(
        async_session, test_user, kind, ANCHOR - timedelta(days=1), ANCHOR + timedelta(days=5)
    )

    assert sql_side == python_side
    assert sql_side, "dataset should not be empty — the assertion above would be vacuous"


@pytest.mark.asyncio
async def test_days_are_utc_buckets_across_midnight(
    async_session: AsyncSession, test_user: User
) -> None:
    """23:59 and 00:01 belong to different UTC days, and averages are exact."""
    await _seed(async_session, test_user)

    stats, _ = await _both_paths(
        async_session,
        test_user,
        "heart_rate",
        ANCHOR - timedelta(days=1),
        ANCHOR + timedelta(days=5),
    )
    by_day = {stat.day: stat for stat in stats}

    assert by_day[date(2026, 5, 19)] == DailyStat(
        day=date(2026, 5, 19), total=60, count=1, minimum=60
    )
    assert by_day[date(2026, 5, 20)] == DailyStat(
        day=date(2026, 5, 20), total=161, count=2, minimum=80
    )
    # 70 + 71 + 73 = 214 over 3 samples -> the repeating-decimal case.
    assert by_day[date(2026, 5, 21)] == DailyStat(
        day=date(2026, 5, 21), total=214, count=3, minimum=70
    )
    assert by_day[date(2026, 5, 21)].total / by_day[date(2026, 5, 21)].count == 214 / 3


@pytest.mark.asyncio
async def test_day_bucketing_ignores_the_session_timezone(
    async_session: AsyncSession, test_user: User
) -> None:
    """A UTC+14 connection must not shift a single day.

    ``SET LOCAL`` scopes the change to the surrounding transaction, so the
    fixture's connection is never left contaminated for the next test.
    """
    await _seed(async_session, test_user)
    window = (ANCHOR - timedelta(days=1), ANCHOR + timedelta(days=5))

    utc_stats, _ = await _both_paths(async_session, test_user, "heart_rate", *window)

    await async_session.execute(text("SET LOCAL TIME ZONE 'Pacific/Kiritimati'"))
    shifted_stats, python_side = await _both_paths(async_session, test_user, "heart_rate", *window)

    assert shifted_stats == utc_stats
    assert shifted_stats == python_side


@pytest.mark.asyncio
async def test_window_bounds_are_inclusive_then_exclusive(
    async_session: AsyncSession, test_user: User
) -> None:
    """``from_ts`` is included, ``to_ts`` excluded — same as the raw fetch."""
    await _seed(async_session, test_user)
    first_sample_at = ANCHOR - timedelta(minutes=1)

    included, python_included = await _both_paths(
        async_session, test_user, "heart_rate", first_sample_at, ANCHOR + timedelta(minutes=2)
    )
    excluded, python_excluded = await _both_paths(
        async_session,
        test_user,
        "heart_rate",
        first_sample_at + timedelta(seconds=1),
        ANCHOR + timedelta(minutes=2),
    )

    assert included == python_included
    assert excluded == python_excluded
    # The 23:59 sample is in the first window, out of the second.
    assert date(2026, 5, 19) in {stat.day for stat in included}
    assert date(2026, 5, 19) not in {stat.day for stat in excluded}
    # to_ts is exclusive: the 00:02 sample is never counted.
    assert all(stat.total != 161 for stat in included)


@pytest.mark.asyncio
async def test_ordering_and_empty_window(async_session: AsyncSession, test_user: User) -> None:
    """Days come back ascending; a window with no sample yields an empty list."""
    await _seed(async_session, test_user)
    repo = HealthSampleRepository(async_session)

    stats = await repo.fetch_daily_stats(
        test_user.id,
        kind="heart_rate",
        from_ts=ANCHOR - timedelta(days=1),
        to_ts=ANCHOR + timedelta(days=5),
    )
    empty = await repo.fetch_daily_stats(
        test_user.id,
        kind="heart_rate",
        from_ts=ANCHOR + timedelta(days=100),
        to_ts=ANCHOR + timedelta(days=200),
    )

    assert [stat.day for stat in stats] == sorted(stat.day for stat in stats)
    assert empty == []


@pytest.mark.asyncio
async def test_rollup_is_scoped_to_user_and_kind(
    async_session: AsyncSession, test_user: User
) -> None:
    """Neither another user's rows nor another kind may leak into a series."""
    await _seed(async_session, test_user)
    other = User(
        email="rollup-isolation@example.com",
        hashed_password="x",
        full_name="Other",
        is_active=True,
        is_verified=True,
    )
    async_session.add(other)
    await async_session.flush()
    async_session.add(_sample(other.id, "heart_rate", ANCHOR + timedelta(hours=1), 200))
    await async_session.commit()

    repo = HealthSampleRepository(async_session)
    stats = await repo.fetch_daily_stats(
        test_user.id,
        kind="heart_rate",
        from_ts=ANCHOR - timedelta(days=1),
        to_ts=ANCHOR + timedelta(days=5),
    )

    by_day = {stat.day: stat for stat in stats}
    # The other user's 200 bpm would blow both the total and the minimum.
    assert by_day[date(2026, 5, 20)].total == 161
    assert all(stat.minimum >= 60 for stat in stats)
    # steps rows exist on the same days and must not bleed into heart_rate.
    assert by_day[date(2026, 5, 20)].count == 2
