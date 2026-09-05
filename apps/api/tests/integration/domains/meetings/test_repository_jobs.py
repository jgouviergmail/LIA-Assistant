"""MeetingRepository job transitions against REAL PostgreSQL (ADR-258, amended 2026-09-05).

The unit tests of the job mock the repository, so the statements it builds
were never executed by a database until a production meeting was re-driven
every fifteen minutes for two hours because ``fail_or_retry`` wrote the enum
VALUE where the column stores the NAME. Every transition below runs for real
(``async_session`` fixture: outer transaction + SAVEPOINT, nothing persists).
``now()`` is frozen inside that transaction, so time-based cases set the
lease explicitly in the past instead of waiting.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.meetings.error_codes import ERROR_WORKER_LOST
from src.domains.meetings.models import (
    Meeting,
    MeetingAudioFormat,
    MeetingStage,
    MeetingStatus,
)
from src.domains.meetings.repository import MeetingRepository
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration

LEASE_TTL = 300
MAX_ATTEMPTS = 3


async def _make_stopped_meeting(db: AsyncSession, **overrides: object) -> uuid.UUID:
    user = UserFactory.create()
    db.add(user)
    await db.flush()
    meeting = Meeting(
        user_id=user.id,
        status=MeetingStatus.STOPPED,
        audio_format=MeetingAudioFormat.PCM_S16LE_16,
        started_at=datetime(2026, 9, 5, 9, 25, tzinfo=UTC),
        stopped_at=datetime(2026, 9, 5, 9, 26, tzinfo=UTC),
        client_timezone="UTC",
        segment_count=2,
    )
    for key, value in overrides.items():
        setattr(meeting, key, value)
    db.add(meeting)
    await db.flush()
    return meeting.id


async def _row(db: AsyncSession, meeting_id: uuid.UUID) -> Meeting:
    db.expire_all()
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    return result.scalar_one()


async def _expire_lease(db: AsyncSession, meeting_id: uuid.UUID) -> None:
    await db.execute(
        text("UPDATE meetings SET lease_expires_at = now() - interval '1 hour' WHERE id = :id"),
        {"id": str(meeting_id)},
    )


# ------------------------------------------------------------- fail_or_retry


async def test_fail_or_retry_returns_the_row_to_stopped_then_dead_letters_at_the_budget(
    async_session: AsyncSession,
) -> None:
    """The 2026-09-05 incident: the transition must COMMIT and the row must read back."""
    meeting_id = await _make_stopped_meeting(async_session)
    repo = MeetingRepository(async_session)
    statuses: list[MeetingStatus] = []
    for _ in range(MAX_ATTEMPTS):
        assert await repo.claim_stopped(meeting_id, worker_id="w1", lease_ttl_s=LEASE_TTL)
        statuses.append(
            await repo.fail_or_retry(
                meeting_id, code="synthesis_failed", message="boom", max_attempts=MAX_ATTEMPTS
            )
        )
        row = await _row(async_session, meeting_id)
        assert row.status is statuses[-1]
        assert row.last_error_code == "synthesis_failed"
        assert row.lease_expires_at is None and row.worker_id is None and row.stage is None
    assert statuses == [MeetingStatus.STOPPED, MeetingStatus.STOPPED, MeetingStatus.FAILED]
    assert (await _row(async_session, meeting_id)).attempts == MAX_ATTEMPTS


async def test_release_unprocessed_gives_the_attempt_back(async_session: AsyncSession) -> None:
    meeting_id = await _make_stopped_meeting(async_session)
    repo = MeetingRepository(async_session)
    assert await repo.claim_stopped(meeting_id, worker_id="w1", lease_ttl_s=LEASE_TTL)
    await repo.release_unprocessed(meeting_id, code="usage_limit", message="")
    row = await _row(async_session, meeting_id)
    assert row.status is MeetingStatus.STOPPED
    assert row.attempts == 0
    assert row.last_error_code == "usage_limit"


# ------------------------------------------------------ heartbeat + checkpoint


async def test_heartbeat_is_refused_to_a_foreign_worker(async_session: AsyncSession) -> None:
    meeting_id = await _make_stopped_meeting(async_session)
    repo = MeetingRepository(async_session)
    assert await repo.claim_stopped(meeting_id, worker_id="w1", lease_ttl_s=LEASE_TTL)
    assert (
        await repo.heartbeat(
            meeting_id, worker_id="w2", lease_ttl_s=LEASE_TTL, stage=MeetingStage.TRANSCRIBING
        )
        is False
    )
    assert (await _row(async_session, meeting_id)).stage is MeetingStage.NORMALIZING


async def test_heartbeat_persists_the_checkpoint_it_carries(async_session: AsyncSession) -> None:
    meeting_id = await _make_stopped_meeting(async_session)
    repo = MeetingRepository(async_session)
    assert await repo.claim_stopped(meeting_id, worker_id="w1", lease_ttl_s=LEASE_TTL)
    assert await repo.heartbeat(
        meeting_id,
        worker_id="w1",
        lease_ttl_s=LEASE_TTL,
        stage=MeetingStage.TRANSCRIBING,
        values={"audio_path": "u/m/audio.webm", "audio_duration_seconds": 33.0, "audio_gaps": 1},
    )
    row = await _row(async_session, meeting_id)
    assert row.stage is MeetingStage.TRANSCRIBING
    assert (row.audio_path, row.audio_duration_seconds, row.audio_gaps) == (
        "u/m/audio.webm",
        33.0,
        1,
    )


async def test_a_checkpoint_survives_fail_or_retry_and_requeue_for_retry(
    async_session: AsyncSession,
) -> None:
    """What an attempt acquired stays on the row for the next one."""
    meeting_id = await _make_stopped_meeting(async_session)
    repo = MeetingRepository(async_session)
    assert await repo.claim_stopped(meeting_id, worker_id="w1", lease_ttl_s=LEASE_TTL)
    await repo.heartbeat(
        meeting_id,
        worker_id="w1",
        lease_ttl_s=LEASE_TTL,
        stage=MeetingStage.SYNTHESIZING,
        values={"audio_path": "u/m/audio.webm", "transcript_encrypted": "cipher"},
    )
    await repo.fail_or_retry(meeting_id, code="synthesis_failed", message="", max_attempts=1)
    assert (await _row(async_session, meeting_id)).status is MeetingStatus.FAILED
    assert await repo.requeue_for_retry(
        meeting_id, from_statuses=(MeetingStatus.STOPPED, MeetingStatus.FAILED)
    )
    row = await _row(async_session, meeting_id)
    assert row.status is MeetingStatus.STOPPED and row.attempts == 0
    assert row.audio_path == "u/m/audio.webm" and row.transcript_encrypted == "cipher"


# ------------------------------------------------------------------- complete


async def test_complete_resets_the_budget_and_clears_the_lease(
    async_session: AsyncSession,
) -> None:
    meeting_id = await _make_stopped_meeting(async_session)
    repo = MeetingRepository(async_session)
    assert await repo.claim_stopped(meeting_id, worker_id="w1", lease_ttl_s=LEASE_TTL)
    assert await repo.complete(meeting_id, worker_id="w1", values={"audio_path": "u/m/a.webm"})
    row = await _row(async_session, meeting_id)
    assert row.status is MeetingStatus.READY
    assert row.attempts == 0 and row.lease_expires_at is None and row.worker_id is None


# --------------------------------------------------------------------- reaper


async def test_an_expired_lease_below_the_budget_is_requeued(async_session: AsyncSession) -> None:
    meeting_id = await _make_stopped_meeting(async_session)
    repo = MeetingRepository(async_session)
    assert await repo.claim_stopped(meeting_id, worker_id="w1", lease_ttl_s=LEASE_TTL)
    await _expire_lease(async_session, meeting_id)
    assert await repo.requeue_expired_leases(MAX_ATTEMPTS) == (1, 0)
    row = await _row(async_session, meeting_id)
    assert row.status is MeetingStatus.STOPPED and row.last_error_code is None


async def test_an_expired_lease_at_the_budget_is_dead_lettered(async_session: AsyncSession) -> None:
    meeting_id = await _make_stopped_meeting(async_session, attempts=MAX_ATTEMPTS - 1)
    repo = MeetingRepository(async_session)
    assert await repo.claim_stopped(meeting_id, worker_id="w1", lease_ttl_s=LEASE_TTL)
    await _expire_lease(async_session, meeting_id)
    assert await repo.requeue_expired_leases(MAX_ATTEMPTS) == (0, 1)
    row = await _row(async_session, meeting_id)
    assert row.status is MeetingStatus.FAILED
    assert row.last_error_code == ERROR_WORKER_LOST


async def test_a_live_lease_is_left_alone(async_session: AsyncSession) -> None:
    meeting_id = await _make_stopped_meeting(async_session)
    repo = MeetingRepository(async_session)
    assert await repo.claim_stopped(meeting_id, worker_id="w1", lease_ttl_s=LEASE_TTL)
    assert await repo.requeue_expired_leases(MAX_ATTEMPTS) == (0, 0)
    assert (await _row(async_session, meeting_id)).status is MeetingStatus.PROCESSING


# ---------------------------------------------------------- delete + retention


async def test_delete_unless_leased_refuses_a_live_lease_and_accepts_an_expired_one(
    async_session: AsyncSession,
) -> None:
    meeting_id = await _make_stopped_meeting(async_session)
    repo = MeetingRepository(async_session)
    assert await repo.claim_stopped(meeting_id, worker_id="w1", lease_ttl_s=LEASE_TTL)
    assert await repo.delete_unless_leased(meeting_id) is False
    await _expire_lease(async_session, meeting_id)
    assert await repo.delete_unless_leased(meeting_id) is True
    result = await async_session.execute(select(Meeting.id).where(Meeting.id == meeting_id))
    assert result.first() is None


async def test_retention_never_offers_a_failed_meeting_for_purge(
    async_session: AsyncSession,
) -> None:
    """A failed meeting keeps its audio until its owner deletes it: a retry needs it."""
    failed_id = await _make_stopped_meeting(
        async_session, status=MeetingStatus.FAILED, audio_path="u/f/audio.webm"
    )
    ready_id = await _make_stopped_meeting(
        async_session, status=MeetingStatus.READY, audio_path="u/r/audio.webm"
    )
    repo = MeetingRepository(async_session)
    due = {meeting.id for meeting in await repo.fetch_audio_to_purge(limit=50)}
    assert ready_id in due
    assert failed_id not in due
