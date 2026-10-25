"""Meeting imports against REAL PostgreSQL (owner request 2026-10-24).

What only the database proves: ONE import in progress per account is held by
a partial unique index on the member NAME (and a live recording does not
count against it); a chunk is accounted only while the row is ``uploading``
and leaves it ``uploading``; completion is ``uploading → stopped`` and nothing
else; and the abandon sweep fails exactly the imports gone silent — judged on
the last chunk, never on the meeting's own date, which is its recording's.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.meetings.error_codes import ERROR_IMPORT_INCOMPLETE
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.meetings.repository import MeetingRepository
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration

#: Recorded weeks ago: the abandon sweep must never read this date.
RECORDED = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


async def _user(db: AsyncSession) -> uuid.UUID:
    user = UserFactory.create()
    db.add(user)
    await db.flush()
    return user.id


def _meeting(
    user_id: uuid.UUID, status: MeetingStatus, audio_format: MeetingAudioFormat
) -> Meeting:
    return Meeting(
        user_id=user_id,
        status=status,
        audio_format=audio_format,
        started_at=RECORDED,
        client_timezone="UTC",
    )


async def _row(db: AsyncSession, meeting_id: uuid.UUID) -> Meeting:
    db.expire_all()
    return (await db.execute(select(Meeting).where(Meeting.id == meeting_id))).scalar_one()


async def test_one_import_per_account_while_a_recording_runs_beside_it(
    async_session: AsyncSession,
) -> None:
    user_id = await _user(async_session)
    async_session.add_all(
        [
            _meeting(user_id, MeetingStatus.RECORDING, MeetingAudioFormat.WEBM_OPUS),
            _meeting(user_id, MeetingStatus.UPLOADING, MeetingAudioFormat.IMPORT_MP3),
        ]
    )
    await async_session.flush()

    with pytest.raises(IntegrityError, match="uq_meetings_one_import_per_user"):
        async with async_session.begin_nested():
            async_session.add(
                _meeting(user_id, MeetingStatus.UPLOADING, MeetingAudioFormat.IMPORT_WAV)
            )
            await async_session.flush()

    # Another account imports freely.
    other = await _user(async_session)
    async_session.add(_meeting(other, MeetingStatus.UPLOADING, MeetingAudioFormat.IMPORT_M4A))
    await async_session.flush()


async def test_a_chunk_is_accounted_only_while_uploading_and_completion_stops_it(
    async_session: AsyncSession,
) -> None:
    user_id = await _user(async_session)
    meeting = _meeting(user_id, MeetingStatus.UPLOADING, MeetingAudioFormat.IMPORT_WAV)
    async_session.add(meeting)
    await async_session.flush()
    repo = MeetingRepository(async_session)
    uploading = (MeetingStatus.UPLOADING,)

    recorded = await repo.record_segment(
        meeting.id,
        sequence=1,
        added_bytes=4096,
        accepting=uploading,
        status_after=MeetingStatus.UPLOADING,
    )
    assert recorded == (MeetingStatus.UPLOADING, 2, 4096)
    # The import door never stops a recording, nor resumes one.
    assert not await repo.stop(
        meeting.id, stopped_at=RECORDED, segment_count=2, accepting=(MeetingStatus.RECORDING,)
    )
    assert await repo.stop(meeting.id, stopped_at=RECORDED, segment_count=2, accepting=uploading)
    row = await _row(async_session, meeting.id)
    assert row.status is MeetingStatus.STOPPED and row.segment_count == 2

    # Stopped: a late chunk is refused, the total untouched.
    late = await repo.record_segment(
        meeting.id,
        sequence=2,
        added_bytes=10,
        accepting=uploading,
        status_after=MeetingStatus.UPLOADING,
    )
    assert late is None
    assert (await _row(async_session, meeting.id)).audio_bytes == 4096


async def test_the_sweep_fails_the_imports_gone_silent_and_only_them(
    async_session: AsyncSession,
) -> None:
    user_id = await _user(async_session)
    silent = _meeting(user_id, MeetingStatus.UPLOADING, MeetingAudioFormat.IMPORT_M4A)
    recording = _meeting(user_id, MeetingStatus.RECORDING, MeetingAudioFormat.WEBM_OPUS)
    fresh = _meeting(
        await _user(async_session), MeetingStatus.UPLOADING, MeetingAudioFormat.IMPORT_MP3
    )
    async_session.add_all([silent, recording, fresh])
    await async_session.flush()
    # Read once: `_row` expires the session, and an expired id would reload outside a greenlet.
    silent_id, recording_id, fresh_id = silent.id, recording.id, fresh.id
    # ``now()`` is frozen in this transaction: age the last chunks explicitly.
    for meeting_id, age in ((silent_id, "2 hours"), (recording_id, "2 hours"), (fresh_id, "0")):
        await async_session.execute(
            text(f"UPDATE meetings SET last_segment_at = now() - interval '{age}' WHERE id = :id"),
            {"id": str(meeting_id)},
        )

    failed = await MeetingRepository(async_session).fail_stale_imports(stale_minutes=15)

    assert failed == [(silent_id, user_id, MeetingAudioFormat.IMPORT_M4A)]
    row = await _row(async_session, silent_id)
    assert row.status is MeetingStatus.FAILED and row.last_error_code == ERROR_IMPORT_INCOMPLETE
    # A fresh import — dated weeks back by its recording — and a recording stay.
    assert (await _row(async_session, fresh_id)).status is MeetingStatus.UPLOADING
    assert (await _row(async_session, recording_id)).status is MeetingStatus.RECORDING
