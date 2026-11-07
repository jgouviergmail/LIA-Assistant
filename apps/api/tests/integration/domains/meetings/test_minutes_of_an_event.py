"""An event's minutes, read on PostgreSQL (ADR-372, lot 5): the page and its exact total."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.meetings.repository import MeetingRepository
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


async def _person(db: AsyncSession) -> UUID:
    user = UserFactory.create()
    db.add(user)
    await db.flush()
    return user.id


async def _meeting(db: AsyncSession, user_id: UUID, event_id: str | None, day: int) -> Meeting:
    meeting = Meeting(
        user_id=user_id,
        status=MeetingStatus.READY,
        audio_format=MeetingAudioFormat.PCM_S16LE_16,
        started_at=datetime(2026, 10, day, tzinfo=UTC),
        client_timezone="UTC",
        calendar_event_id=event_id,
    )
    db.add(meeting)
    await db.flush()
    return meeting


async def test_an_event_reads_its_own_minutes_newest_first(async_session: AsyncSession) -> None:
    person = await _person(async_session)
    older = await _meeting(async_session, person, "event-1", 1)
    newer = await _meeting(async_session, person, "event-1", 2)
    await _meeting(async_session, person, "event-2", 3)
    await _meeting(async_session, person, None, 4)

    rows, total = await MeetingRepository(async_session).list_for_user(
        person, limit=1, offset=0, calendar_event_id="event-1"
    )

    assert [row.id for row in rows] == [newer.id]
    assert total == 2
    assert older.id != newer.id


async def test_another_account_s_minutes_never_answer(async_session: AsyncSession) -> None:
    person = await _person(async_session)
    other = await _person(async_session)
    await _meeting(async_session, other, "event-1", 1)

    rows, total = await MeetingRepository(async_session).list_for_user(
        person, limit=10, offset=0, calendar_event_id="event-1"
    )

    assert rows == []
    assert total == 0


async def test_no_event_named_reads_the_whole_list(async_session: AsyncSession) -> None:
    person = await _person(async_session)
    await _meeting(async_session, person, "event-1", 1)
    await _meeting(async_session, person, None, 2)

    rows, total = await MeetingRepository(async_session).list_for_user(person, limit=10, offset=0)

    assert len(rows) == 2
    assert total == 2
