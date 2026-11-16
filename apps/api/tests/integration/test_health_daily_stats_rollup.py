"""Integration tests for the per-day rollup against a real PostgreSQL.

``HealthSampleRepository.fetch_daily_stats`` is what the baseline, variations,
heartbeat and briefing paths read. Since the ADR-148 amendment of 2026-11-14
it counts through the fusion door (``fusion.counted_samples``) and cuts days
at the person's midnight. Both halves are SQL, so both are proven here, on a
real database:

- **Local days.** A sample at 23:30 UTC is the NEXT day in Paris; a day a
  clock change shortens (29 March) or lengthens (25 October) is still one day.
- **Session-timezone independence.** Day bucketing uses an explicit
  ``timezone(<zone>, ...)``; a connection whose ``TimeZone`` is UTC+14 must
  yield exactly the same days. Without the explicit cast this is the bug that
  ships: green in CI (UTC), wrong in production.
- **The fusion.** Two devices measuring one walk count it once: a long sample
  holding a short one, two staggered samples, an identical rate on both; a
  sample overlapping nothing comes out whole; a sample starting before the
  window shares its overlap with one starting inside it.
- **Window bounds** (a row belongs to the window of its start, ``to_ts``
  exclusive), ordering, the empty window, user and kind isolation.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.health_metrics.baseline import DailyStat
from src.domains.health_metrics.models import HealthSample
from src.domains.health_metrics.repository import HealthSampleRepository
from src.domains.users.models import User

pytestmark = pytest.mark.integration

PARIS = ZoneInfo("Europe/Paris")
UTC_ZONE = ZoneInfo("UTC")


def _sample(user_id, kind: str, start: datetime, value: int, *, minutes: float = 1) -> HealthSample:
    return HealthSample(
        user_id=user_id,
        kind=kind,
        date_start=start,
        date_end=start + timedelta(minutes=minutes),
        value=value,
        source="test",
    )


async def _stats(
    session: AsyncSession,
    user: User,
    kind: str,
    zone: ZoneInfo,
    from_ts: datetime,
    to_ts: datetime,
) -> list[DailyStat]:
    return await HealthSampleRepository(session).fetch_daily_stats(
        user.id, kind=kind, zone=zone, from_ts=from_ts, to_ts=to_ts
    )


# =============================================================================
# Local days
# =============================================================================


@pytest.mark.asyncio
async def test_a_day_is_the_person_s_day(async_session: AsyncSession, test_user: User) -> None:
    """23:30 UTC on the 13th is 00:30 on the 14th in Paris: the 14th's steps."""
    evening = datetime(2026, 11, 13, 23, 30, tzinfo=UTC)
    async_session.add_all(
        [
            _sample(test_user.id, "steps", evening, 300),
            _sample(test_user.id, "steps", evening + timedelta(hours=12), 700),
        ]
    )
    await async_session.commit()
    window = (datetime(2026, 11, 12, tzinfo=UTC), datetime(2026, 11, 16, tzinfo=UTC))

    paris = await _stats(async_session, test_user, "steps", PARIS, *window)
    utc = await _stats(async_session, test_user, "steps", UTC_ZONE, *window)

    assert [(stat.day, stat.total) for stat in paris] == [(date(2026, 11, 14), 1000)]
    assert [(stat.day, stat.total) for stat in utc] == [
        (date(2026, 11, 13), 300),
        (date(2026, 11, 14), 700),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("day", "last_instant"),
    [
        # 29 March 2026 lasts 23 hours in Paris: its last minute is 21:59 UTC.
        (date(2026, 3, 29), datetime(2026, 3, 29, 21, 59, tzinfo=UTC)),
        # 25 October 2026 lasts 25 hours: its last minute is 22:59 UTC.
        (date(2026, 10, 25), datetime(2026, 10, 25, 22, 59, tzinfo=UTC)),
    ],
)
async def test_a_day_a_clock_change_shortens_or_lengthens_is_one_day(
    async_session: AsyncSession, test_user: User, day: date, last_instant: datetime
) -> None:
    first_instant = datetime.combine(day, datetime.min.time(), tzinfo=PARIS).astimezone(UTC)
    async_session.add_all(
        [
            _sample(test_user.id, "steps", first_instant, 100),
            _sample(test_user.id, "steps", last_instant, 200),
            # The next local day's first minute.
            _sample(test_user.id, "steps", last_instant + timedelta(minutes=1), 400),
        ]
    )
    await async_session.commit()

    stats = await _stats(
        async_session,
        test_user,
        "steps",
        PARIS,
        first_instant - timedelta(days=1),
        last_instant + timedelta(days=1),
    )

    assert [(stat.day, stat.total) for stat in stats] == [
        (day, 300),
        (day + timedelta(days=1), 400),
    ]


@pytest.mark.asyncio
async def test_day_bucketing_ignores_the_session_timezone(
    async_session: AsyncSession, test_user: User
) -> None:
    """A UTC+14 connection must not shift a single day.

    ``SET LOCAL`` scopes the change to the surrounding transaction, so the
    fixture's connection is never left contaminated for the next test.
    """
    anchor = datetime(2026, 5, 20, tzinfo=UTC)
    async_session.add_all(
        [
            _sample(test_user.id, "heart_rate", anchor - timedelta(minutes=1), 60),
            _sample(test_user.id, "heart_rate", anchor + timedelta(minutes=1), 80),
            _sample(test_user.id, "steps", anchor + timedelta(hours=21, minutes=30), 500),
        ]
    )
    await async_session.commit()
    window = (anchor - timedelta(days=1), anchor + timedelta(days=2))

    before = {
        kind: await _stats(async_session, test_user, kind, PARIS, *window)
        for kind in ("heart_rate", "steps")
    }
    await async_session.execute(text("SET LOCAL TIME ZONE 'Pacific/Kiritimati'"))
    after = {
        kind: await _stats(async_session, test_user, kind, PARIS, *window)
        for kind in ("heart_rate", "steps")
    }

    assert after == before
    # 23:59 and 00:01 UTC are both the 20th in Paris (01:59 and 02:01).
    assert before["heart_rate"] == [
        DailyStat(day=date(2026, 5, 20), total=140, count=2, minimum=60)
    ]
    # 21:30 UTC is 23:30 in Paris: still the 20th.
    assert [(stat.day, stat.total) for stat in before["steps"]] == [(date(2026, 5, 20), 500)]


# =============================================================================
# The fusion: one walk measured twice counts once
# =============================================================================


@pytest.mark.asyncio
async def test_a_long_sample_holding_a_short_one_counts_the_higher_rate(
    async_session: AsyncSession, test_user: User
) -> None:
    """The phone's 10 minutes at 100/min hold the watch's 2 minutes at 150/min.

    Slices: 4 min at 100, 2 min at max(100, 150) = 150, 4 min at 100 → 1100,
    where the raw sum said 1000 + 300 = 1300.
    """
    start = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
    async_session.add_all(
        [
            _sample(test_user.id, "steps", start, 1000, minutes=10),
            _sample(test_user.id, "steps", start + timedelta(minutes=4), 300, minutes=2),
        ]
    )
    await async_session.commit()

    stats = await _stats(
        async_session,
        test_user,
        "steps",
        PARIS,
        start - timedelta(hours=1),
        start + timedelta(hours=1),
    )

    assert [stat.total for stat in stats] == [1100]


@pytest.mark.asyncio
async def test_staggered_samples_and_an_identical_rate_count_once(
    async_session: AsyncSession, test_user: User
) -> None:
    """Two devices agreeing on a walk: the overlap counts once, whatever its shape."""
    start = datetime(2026, 11, 14, 14, 0, tzinfo=UTC)
    async_session.add_all(
        [
            # Staggered: [0, 10) at 50/min and [5, 15) at 50/min → 15 min at 50.
            _sample(test_user.id, "steps", start, 500, minutes=10),
            _sample(test_user.id, "steps", start + timedelta(minutes=5), 500, minutes=10),
            # Alone an hour later: whole.
            _sample(test_user.id, "steps", start + timedelta(hours=1), 123, minutes=3),
        ]
    )
    await async_session.commit()

    stats = await _stats(
        async_session,
        test_user,
        "steps",
        PARIS,
        start - timedelta(hours=1),
        start + timedelta(hours=3),
    )

    assert [stat.total for stat in stats] == [750 + 123]


@pytest.mark.asyncio
async def test_samples_that_never_overlap_add_up_exactly(
    async_session: AsyncSession, test_user: User
) -> None:
    """The fusion changes nothing where nothing overlaps — one per minute, odd values."""
    start = datetime(2026, 11, 14, 7, 0, tzinfo=UTC)
    values = [17, 1, 999, 3, 250, 7, 41]
    async_session.add_all(
        [
            _sample(test_user.id, "steps", start + timedelta(minutes=index), value)
            for index, value in enumerate(values)
        ]
    )
    await async_session.commit()

    stats = await _stats(
        async_session, test_user, "steps", PARIS, start, start + timedelta(hours=1)
    )

    assert [stat.total for stat in stats] == [sum(values)]


@pytest.mark.asyncio
async def test_heart_rate_readings_are_never_fused(
    async_session: AsyncSession, test_user: User
) -> None:
    """Two overlapping readings are two observations: averaged, not deduplicated."""
    start = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)
    async_session.add_all(
        [
            _sample(test_user.id, "heart_rate", start, 60, minutes=5),
            _sample(test_user.id, "heart_rate", start + timedelta(minutes=1), 90, minutes=5),
        ]
    )
    await async_session.commit()

    stats = await _stats(
        async_session, test_user, "heart_rate", PARIS, start, start + timedelta(hours=1)
    )

    assert stats == [DailyStat(day=date(2026, 11, 14), total=150, count=2, minimum=60)]


@pytest.mark.asyncio
async def test_adjacent_windows_add_up_to_the_window_that_holds_them(
    async_session: AsyncSession, test_user: User
) -> None:
    """A sample starting before a window still splits the overlap the window reads.

    The phone's [23:50, 00:10) and the watch's [00:00, 00:05) at a higher rate:
    the slice [00:00, 00:05) counts once, in the day it starts on, whichever
    window reads it — so yesterday plus today equals both days read at once.
    """
    midnight = datetime(2026, 11, 14, tzinfo=PARIS).astimezone(UTC)
    async_session.add_all(
        [
            _sample(test_user.id, "steps", midnight - timedelta(minutes=10), 200, minutes=20),
            _sample(test_user.id, "steps", midnight, 100, minutes=5),
        ]
    )
    await async_session.commit()
    day = timedelta(days=1)

    yesterday = await _stats(async_session, test_user, "steps", PARIS, midnight - day, midnight)
    today = await _stats(async_session, test_user, "steps", PARIS, midnight, midnight + day)
    both = await _stats(async_session, test_user, "steps", PARIS, midnight - day, midnight + day)

    # [23:50, 00:00) at 10/min = 100; [00:00, 00:05) at max(10, 20) = 100; [00:05, 00:10) = 50.
    assert [(stat.day, stat.total) for stat in yesterday] == [(date(2026, 11, 13), 100)]
    assert [(stat.day, stat.total) for stat in today] == [(date(2026, 11, 14), 150)]
    assert both == yesterday + today


# =============================================================================
# Bounds, ordering, isolation
# =============================================================================


@pytest.mark.asyncio
async def test_window_bounds_are_inclusive_then_exclusive(
    async_session: AsyncSession, test_user: User
) -> None:
    """A row belongs to the window of its start: ``from_ts`` in, ``to_ts`` out."""
    start = datetime(2026, 5, 20, 8, 0, tzinfo=UTC)
    async_session.add_all(
        [
            _sample(test_user.id, "heart_rate", start, 61),
            _sample(test_user.id, "heart_rate", start + timedelta(minutes=5), 75),
        ]
    )
    await async_session.commit()

    included = await _stats(
        async_session, test_user, "heart_rate", PARIS, start, start + timedelta(minutes=5)
    )
    excluded = await _stats(
        async_session,
        test_user,
        "heart_rate",
        PARIS,
        start + timedelta(seconds=1),
        start + timedelta(minutes=10),
    )

    assert [stat.total for stat in included] == [61]
    assert [stat.total for stat in excluded] == [75]


@pytest.mark.asyncio
async def test_ordering_and_empty_window(async_session: AsyncSession, test_user: User) -> None:
    """Days come back ascending; a window with no sample yields an empty list."""
    base = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    async_session.add_all(
        [_sample(test_user.id, "steps", base + timedelta(days=offset), 100) for offset in (2, 0, 1)]
    )
    await async_session.commit()

    stats = await _stats(
        async_session, test_user, "steps", PARIS, base - timedelta(days=1), base + timedelta(days=5)
    )
    empty = await _stats(
        async_session,
        test_user,
        "steps",
        PARIS,
        base + timedelta(days=100),
        base + timedelta(days=200),
    )

    assert [stat.day for stat in stats] == [date(2026, 5, 20), date(2026, 5, 21), date(2026, 5, 22)]
    assert empty == []


@pytest.mark.asyncio
async def test_rollup_is_scoped_to_user_and_kind(
    async_session: AsyncSession, test_user: User
) -> None:
    """Neither another user's rows nor another kind may leak into a series."""
    start = datetime(2026, 5, 20, 9, 0, tzinfo=UTC)
    other = User(
        email="rollup-isolation@example.com",
        hashed_password="x",
        full_name="Other",
        is_active=True,
        is_verified=True,
    )
    async_session.add(other)
    await async_session.flush()
    async_session.add_all(
        [
            _sample(test_user.id, "steps", start, 1000, minutes=10),
            # The other person's overlapping walk must not fuse into this one.
            _sample(other.id, "steps", start, 5000, minutes=10),
            _sample(test_user.id, "heart_rate", start, 70, minutes=10),
        ]
    )
    await async_session.commit()

    stats = await _stats(
        async_session, test_user, "steps", PARIS, start, start + timedelta(hours=1)
    )

    assert [stat.total for stat in stats] == [1000]
