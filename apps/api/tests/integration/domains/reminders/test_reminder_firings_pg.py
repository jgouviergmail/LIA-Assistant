"""A fired reminder is postponed once, by its owner, while its window is open.

ADR-268 amendment 2026-11-16, proved on a real PostgreSQL server because the
guarantees live there: the occurrence's row lock serialises two presses (two
devices postpone it ONCE), the copy and the mark commit together, the foreign
key forgets a deleted reminder without losing the occurrence, and the purge
takes only closed windows, in bounded batches.

Every row is REALLY committed (two sessions must see each other's writes) and
removed with its account at the end.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundError
from src.domains.reminders.firing_repository import ReminderFiringRepository
from src.domains.reminders.firing_service import ReminderFiringService, SnoozeResult
from src.domains.reminders.firings import (
    FiringSurface,
    SnoozeChoice,
    SnoozeDelays,
    SnoozeOutcome,
    StopOutcome,
    snooze_instant,
)
from src.domains.reminders.models import Reminder, ReminderFiring, ReminderStatus
from src.domains.users.models import User

pytestmark = pytest.mark.integration

PARIS = "Europe/Paris"
#: A fixed present, far from any clock change: every instant below derives from it.
NOW = datetime(2026, 11, 18, 14, 0, tzinfo=UTC)


@dataclass(frozen=True)
class Db:
    """Sessions whose writes really commit, and the mark of their accounts."""

    maker: async_sessionmaker[AsyncSession]
    marker: str


def _once(at: datetime) -> dict[str, Any]:
    local = at.astimezone(ZoneInfo(PARIS))
    return {
        "freq": "once",
        "interval": 1,
        "anchor_date": local.date().isoformat(),
        "times": {"mode": "at", "at": [{"hour": local.hour, "minute": local.minute}]},
    }


def _daily(hour: int) -> dict[str, Any]:
    return {
        "freq": "daily",
        "interval": 1,
        "anchor_date": "2026-11-01",
        "times": {"mode": "at", "at": [{"hour": hour, "minute": 0}]},
    }


@pytest_asyncio.fixture
async def db(async_engine: Any, test_database_url: str) -> AsyncIterator[Db]:
    """Committing sessions; every account they made is removed at the end."""
    engine = create_async_engine(test_database_url, echo=False)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    marker = f"reminder_firings_{uuid4().hex}"
    yield Db(maker, marker)
    async with maker() as session:
        await session.execute(delete(User).where(User.email.like(f"{marker}%")))
        await session.commit()
    await engine.dispose()


async def _account(db: Db) -> UUID:
    async with db.maker() as session:
        user = User(
            email=f"{db.marker}_{uuid4().hex[:8]}@example.com",
            hashed_password="x",
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.commit()
        return UUID(str(user.id))


async def _reminder(
    db: Db,
    owner: UUID,
    *,
    recurrence: dict[str, Any],
    trigger_at: datetime,
    status: ReminderStatus = ReminderStatus.PROCESSING,
) -> Reminder:
    async with db.maker() as session:
        reminder = Reminder(
            user_id=owner,
            content="appeler la banque",
            original_message="rappelle-moi d'appeler la banque",
            recurrence=recurrence,
            trigger_at=trigger_at,
            user_timezone=PARIS,
            status=status.value,
        )
        session.add(reminder)
        await session.commit()
        return reminder


async def _fire(db: Db, reminder_id: UUID, *, fired_at: datetime = NOW) -> UUID:
    """The scheduler's record of the occurrence, as it writes it before delivery."""
    async with db.maker() as session:
        reminder = await session.get(Reminder, reminder_id)
        assert reminder is not None
        offer = await ReminderFiringService(session).record(reminder, fired_at=fired_at)
        await session.commit()
        return offer.firing_id


async def _snooze(
    db: Db,
    owner: UUID,
    firing_id: UUID,
    choice: SnoozeChoice,
    *,
    now: datetime = NOW,
    zone: str = PARIS,
) -> SnoozeResult:
    async with db.maker() as session:
        result = await ReminderFiringService(session).snooze(
            firing_id, owner, choice, zone=zone, now=now, surface=FiringSurface.CHAT
        )
        await session.commit()
        return result


async def _copies(db: Db, owner: UUID) -> list[Reminder]:
    """The reminders a snooze created (they alone carry the first request)."""
    async with db.maker() as session:
        rows = await session.execute(
            select(Reminder).where(Reminder.user_id == owner, Reminder.first_asked_at.is_not(None))
        )
        return list(rows.scalars().all())


async def _firing(db: Db, firing_id: UUID) -> ReminderFiring | None:
    async with db.maker() as session:
        return await session.get(ReminderFiring, firing_id)


async def test_a_one_shot_is_postponed_after_it_is_gone(db: Db) -> None:
    """The settlement deletes the one-shot; its occurrence still knows what to say."""
    owner = await _account(db)
    reminder = await _reminder(db, owner, recurrence=_once(NOW), trigger_at=NOW)
    firing_id = await _fire(db, reminder.id)
    async with db.maker() as session:  # the settlement of a consumed one-shot
        await session.execute(delete(Reminder).where(Reminder.id == reminder.id))
        await session.commit()
    kept = await _firing(db, firing_id)
    assert kept is not None and kept.reminder_id is None  # SET NULL, the row kept

    result = await _snooze(db, owner, firing_id, SnoozeChoice.SHORT)

    expected = NOW + timedelta(minutes=settings.reminder_snooze_short_minutes)
    assert result.outcome is SnoozeOutcome.SNOOZED
    assert result.snoozed_until == expected
    (copy,) = await _copies(db, owner)
    assert copy.trigger_at == expected
    assert copy.status == ReminderStatus.PENDING.value
    assert copy.recurrence_spec.freq == "once"
    assert copy.content == "appeler la banque"
    assert copy.original_message == "rappelle-moi d'appeler la banque"
    assert copy.first_asked_at == reminder.created_at
    firing = await _firing(db, firing_id)
    assert firing is not None and firing.snoozed_until == expected


async def test_a_copy_postponed_again_keeps_the_first_request(db: Db) -> None:
    owner = await _account(db)
    first = await _reminder(db, owner, recurrence=_once(NOW), trigger_at=NOW)
    await _snooze(db, owner, await _fire(db, first.id), SnoozeChoice.SHORT)
    (copy,) = await _copies(db, owner)

    later = NOW + timedelta(minutes=settings.reminder_snooze_short_minutes)
    second_firing = await _fire(db, copy.id, fired_at=later)
    await _snooze(db, owner, second_firing, SnoozeChoice.SHORT, now=later)

    copies = await _copies(db, owner)
    assert len(copies) == 2
    assert {c.first_asked_at for c in copies} == {first.created_at}


async def test_two_presses_from_two_devices_postpone_once(db: Db) -> None:
    owner = await _account(db)
    reminder = await _reminder(db, owner, recurrence=_once(NOW), trigger_at=NOW)
    firing_id = await _fire(db, reminder.id)

    async with db.maker() as first, db.maker() as second:
        verdict_a = await ReminderFiringService(first).snooze(
            firing_id, owner, SnoozeChoice.SHORT, zone=PARIS, now=NOW, surface=FiringSurface.CHAT
        )
        # The second press waits on the occurrence's lock the first one holds.
        pressed = asyncio.create_task(
            ReminderFiringService(second).snooze(
                firing_id,
                owner,
                SnoozeChoice.LONG,
                zone=PARIS,
                now=NOW,
                surface=FiringSurface.PUSH,
            )
        )
        await asyncio.sleep(0.3)
        assert not pressed.done(), "the second press did not wait for the first"
        await first.commit()
        verdict_b = await asyncio.wait_for(pressed, timeout=10)
        await second.commit()

    assert verdict_a.outcome is SnoozeOutcome.SNOOZED
    assert verdict_b.outcome is SnoozeOutcome.ALREADY_SNOOZED
    assert verdict_b.snoozed_until == verdict_a.snoozed_until
    assert len(await _copies(db, owner)) == 1


async def test_a_press_after_the_window_creates_nothing(db: Db) -> None:
    owner = await _account(db)
    reminder = await _reminder(db, owner, recurrence=_once(NOW), trigger_at=NOW)
    firing_id = await _fire(db, reminder.id)
    late = NOW + timedelta(hours=settings.reminder_snooze_window_hours)

    result = await _snooze(db, owner, firing_id, SnoozeChoice.SHORT, now=late)

    assert result.outcome is SnoozeOutcome.EXPIRED
    assert await _copies(db, owner) == []


async def test_a_postponement_onto_the_series_next_occurrence_is_refused(db: Db) -> None:
    """« Tomorrow morning » on a daily reminder at that hour: the series says it anyway."""
    owner = await _account(db)
    morning = settings.reminder_snooze_morning_hour
    tomorrow_morning = snooze_instant(
        SnoozeChoice.MORNING,
        now=NOW,
        zone=ZoneInfo(PARIS),
        delays=SnoozeDelays.from_settings(),
    )
    series = await _reminder(
        db,
        owner,
        recurrence=_daily(morning),
        trigger_at=tomorrow_morning,
        status=ReminderStatus.PENDING,
    )
    firing_id = await _fire(db, series.id)

    refused = await _snooze(db, owner, firing_id, SnoozeChoice.MORNING)
    accepted = await _snooze(db, owner, firing_id, SnoozeChoice.SHORT)

    assert refused.outcome is SnoozeOutcome.COLLIDES
    assert refused.next_occurrence_at == tomorrow_morning
    assert accepted.outcome is SnoozeOutcome.SNOOZED
    assert len(await _copies(db, owner)) == 1


async def test_the_accounts_present_zone_places_tomorrow_morning(db: Db) -> None:
    """The person moved since the reminder was set: the morning is where they are."""
    owner = await _account(db)
    reminder = await _reminder(db, owner, recurrence=_once(NOW), trigger_at=NOW)
    firing_id = await _fire(db, reminder.id)

    result = await _snooze(db, owner, firing_id, SnoozeChoice.MORNING, zone="America/New_York")

    (copy,) = await _copies(db, owner)
    assert copy.user_timezone == "America/New_York"
    local = copy.trigger_at.astimezone(ZoneInfo("America/New_York"))
    assert (local.hour, local.minute) == (settings.reminder_snooze_morning_hour, 0)
    assert result.snoozed_until == copy.trigger_at


async def test_another_account_cannot_read_or_press_an_occurrence(db: Db) -> None:
    owner = await _account(db)
    stranger = await _account(db)
    reminder = await _reminder(db, owner, recurrence=_once(NOW), trigger_at=NOW)
    firing_id = await _fire(db, reminder.id)

    async with db.maker() as session:
        service = ReminderFiringService(session)
        with pytest.raises(ResourceNotFoundError):
            await service.state(firing_id, stranger, now=NOW)
        with pytest.raises(ResourceNotFoundError):
            await service.snooze(
                firing_id,
                stranger,
                SnoozeChoice.SHORT,
                zone=PARIS,
                now=NOW,
                surface=FiringSurface.CHAT,
            )
        with pytest.raises(ResourceNotFoundError):
            await service.stop(firing_id, stranger, now=NOW, surface=FiringSurface.CHAT)
        await session.rollback()
    assert await _copies(db, owner) == []
    assert await _copies(db, stranger) == []


async def test_stopping_a_series_deletes_it_and_the_occurrence_stays_postponable(
    db: Db,
) -> None:
    owner = await _account(db)
    series = await _reminder(
        db,
        owner,
        recurrence=_daily(9),
        trigger_at=NOW + timedelta(hours=19),
        status=ReminderStatus.PENDING,
    )
    firing_id = await _fire(db, series.id)
    async with db.maker() as session:
        before = await ReminderFiringService(session).state(firing_id, owner, now=NOW)
    assert before.stoppable is True

    async with db.maker() as session:
        stopped = await ReminderFiringService(session).stop(
            firing_id, owner, now=NOW, surface=FiringSurface.TELEGRAM
        )
        await session.commit()
    async with db.maker() as session:
        again = await ReminderFiringService(session).stop(
            firing_id, owner, now=NOW, surface=FiringSurface.CHAT
        )
        after = await ReminderFiringService(session).state(firing_id, owner, now=NOW)
        await session.commit()

    assert stopped is StopOutcome.STOPPED
    assert again is StopOutcome.ALREADY_STOPPED
    assert after.stoppable is False
    async with db.maker() as session:
        assert await session.get(Reminder, series.id) is None
    # « Stopped, then postponed »: the occurrence still holds what it said.
    result = await _snooze(db, owner, firing_id, SnoozeChoice.LONG)
    assert result.outcome is SnoozeOutcome.SNOOZED


async def test_a_one_shot_offers_nothing_to_stop(db: Db) -> None:
    owner = await _account(db)
    reminder = await _reminder(db, owner, recurrence=_once(NOW), trigger_at=NOW)
    async with db.maker() as session:
        claimed = await session.get(Reminder, reminder.id)
        assert claimed is not None
        offer = await ReminderFiringService(session).record(claimed, fired_at=NOW)
        await session.commit()

    assert offer.stoppable is False
    assert offer.snoozable_until == NOW + timedelta(hours=settings.reminder_snooze_window_hours)


async def test_the_purge_takes_closed_windows_only_in_bounded_batches(db: Db) -> None:
    owner = await _account(db)
    window = timedelta(hours=settings.reminder_snooze_window_hours)
    reminder = await _reminder(db, owner, recurrence=_once(NOW), trigger_at=NOW)
    oldest = await _fire(db, reminder.id, fired_at=NOW - window - timedelta(hours=2))
    older = await _fire(db, reminder.id, fired_at=NOW - window - timedelta(hours=1))
    fresh = await _fire(db, reminder.id, fired_at=NOW - timedelta(hours=1))

    async with db.maker() as session:
        first = await ReminderFiringRepository(session).purge_fired_before(NOW - window, limit=1)
        await session.commit()
    assert first == 1
    assert await _firing(db, oldest) is None
    assert await _firing(db, older) is not None

    async with db.maker() as session:
        await ReminderFiringService(session).purge_expired(now=NOW)
        await session.commit()
    assert await _firing(db, older) is None
    assert await _firing(db, fresh) is not None
    async with db.maker() as session:
        left = await session.scalar(
            select(func.count()).select_from(ReminderFiring).where(ReminderFiring.user_id == owner)
        )
    assert left == 1
