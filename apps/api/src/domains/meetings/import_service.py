"""Importing a meeting from a file — WAV, MP3 or M4A (owner request 2026-10-24).

A file the person already holds (a phone's voice memo, a recorder's WAV)
becomes a meeting like a recording does: it is admitted by the same refusals
(``MeetingService.admit``), its bytes travel in chunks onto the same durable
row — ``uploading``, one per account, enforced by the database — and once every
chunk is there the row is ``stopped`` and processing takes it as it takes a
recording. Every bound is published before a byte is sent (ADR-184) and
checked before a byte touches the disk; the first chunk must START as the
format it claims, because ffmpeg will read it through that format's demuxer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, NoReturn

import structlog
from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.meetings.audio_store import AudioStorageError
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus, is_import
from src.domains.meetings.schemas import (
    MeetingImportComplete,
    MeetingImportLimits,
    MeetingImportRequest,
    MeetingImportResponse,
    MeetingSegmentAck,
)
from src.domains.meetings.service import (
    MeetingService,
    raise_meeting_conflict,
    raise_meeting_storage_unavailable,
    raise_meeting_too_large,
)
from src.infrastructure.observability.metrics_meetings import meeting_imports_total

logger = structlog.get_logger(__name__)

#: Missing chunks named in a refusal: enough to retry, never the whole list.
_MISSING_SHOWN = 20


def import_signature_matches(audio_format: MeetingAudioFormat, head: bytes) -> bool:
    """Whether a file's first bytes are the format it claims.

    WAV is a RIFF/WAVE container; an MP3 opens on an ID3 tag or an MPEG frame
    sync (eleven set bits); an M4A is an ISO media file, ``ftyp`` at offset 4.
    Anything else — a renamed file, a playlist, a concat script — is refused.
    """
    if audio_format is MeetingAudioFormat.IMPORT_WAV:
        return head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    if audio_format is MeetingAudioFormat.IMPORT_MP3:
        return head[:3] == b"ID3" or (len(head) >= 2 and head[0] == 0xFF and head[1] >= 0xE0)
    if audio_format is MeetingAudioFormat.IMPORT_M4A:
        return head[4:8] == b"ftyp"
    return False


def max_import_chunks() -> int:
    """Chunks the largest accepted file travels in — the bound on every chunk number.

    Without it, one chunk numbered 10^9 and a completion would make the server
    enumerate a billion missing chunks.
    """
    return -(-settings.meetings_import_max_bytes // settings.meetings_import_chunk_max_bytes)


def import_limits() -> MeetingImportLimits:
    """Every bound an import is held to — the client reads them before choosing a file."""
    return MeetingImportLimits(
        max_bytes=settings.meetings_import_max_bytes,
        chunk_max_bytes=settings.meetings_import_chunk_max_bytes,
        max_duration_minutes=settings.meetings_max_duration_minutes,
    )


def _refuse(status_code: int, code: str, **extra: Any) -> NoReturn:
    raise BaseAPIException(
        status_code=status_code,
        detail={"code": code, **extra},
        log_event=f"meeting_{code}",
        **extra,
    )


class MeetingImportService:
    """The three acts of an import: open it, send a chunk, complete it."""

    def __init__(self, db: AsyncSession) -> None:
        self.meetings = MeetingService(db)

    async def create(self, user: Any, request: MeetingImportRequest) -> MeetingImportResponse:
        """Open an import once the file's size and the meeting's admission allow it."""
        if not settings.meetings_import_enabled:
            raise_meeting_conflict("import_disabled")
        if request.size_bytes > settings.meetings_import_max_bytes:
            raise_meeting_too_large(
                "import_too_large", max_bytes=settings.meetings_import_max_bytes
            )
        admission = await self.meetings.admit(
            user, language=request.language, template_ref=request.template_ref
        )
        try:
            meeting = await self.meetings.repo.create(
                {
                    "user_id": user.id,
                    "status": MeetingStatus.UPLOADING,
                    "audio_format": request.audio_format,
                    "started_at": request.recorded_at.astimezone(UTC),
                    # The upload's own heartbeat: an import silent too long is abandoned.
                    "last_segment_at": datetime.now(UTC),
                    "client_timezone": request.timezone,
                    **self.meetings.admitted_values(admission),
                }
            )
            await self.meetings.db.commit()
        except IntegrityError:
            await self.meetings.db.rollback()
            raise_meeting_conflict("import_already_running")
        meeting_imports_total.labels(format=request.audio_format.value, outcome="started").inc()
        logger.info(
            "meeting_import_started",
            meeting_id=str(meeting.id),
            audio_format=request.audio_format.value,
            size_bytes=request.size_bytes,
        )
        return MeetingImportResponse(
            id=meeting.id,
            status=meeting.status,
            started_at=meeting.started_at,
            engine=self.meetings.engine_info(admission.engine),
            limits=import_limits(),
        )

    async def accept_chunk(
        self, user_id: uuid.UUID, meeting_id: uuid.UUID, *, sequence: int, body: bytes
    ) -> MeetingSegmentAck:
        """Store one chunk; every bound is checked before a byte touches the disk."""
        meeting = await self.meetings._owned(meeting_id, user_id, lock=True)
        self._require_uploading(meeting)
        if not body:
            raise_meeting_conflict("segment_empty", sequence=sequence)
        if sequence >= max_import_chunks():
            raise_meeting_too_large(
                "import_too_large", max_bytes=settings.meetings_import_max_bytes
            )
        if len(body) > settings.meetings_import_chunk_max_bytes:
            raise_meeting_too_large(
                "chunk_too_large", max_bytes=settings.meetings_import_chunk_max_bytes
            )
        if sequence == 0 and not import_signature_matches(meeting.audio_format, body[:16]):
            meeting_imports_total.labels(format=meeting.audio_format.value, outcome="refused").inc()
            _refuse(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "import_format_mismatch")
        store = self.meetings.store
        replaced = await store.segment_size(user_id, meeting_id, sequence)
        if meeting.audio_bytes - replaced + len(body) > settings.meetings_import_max_bytes:
            raise_meeting_too_large(
                "import_too_large", max_bytes=settings.meetings_import_max_bytes
            )
        try:
            added, _ = await store.write_segment(user_id, meeting_id, sequence, body)
        except AudioStorageError as exc:
            logger.error("meeting_import_write_failed", meeting_id=str(meeting_id), error=str(exc))
            raise_meeting_storage_unavailable()
        recorded = await self.meetings.repo.record_segment(
            meeting_id,
            sequence=sequence,
            added_bytes=added,
            accepting=(MeetingStatus.UPLOADING,),
            status_after=MeetingStatus.UPLOADING,
        )
        if recorded is None:
            raise_meeting_conflict("meeting_not_uploading", status=MeetingStatus.STOPPED.value)
        new_status, segment_count, audio_bytes = recorded
        return MeetingSegmentAck(
            sequence=sequence,
            segment_count=segment_count,
            audio_bytes=audio_bytes,
            status=new_status,
        )

    async def complete(
        self, user_id: uuid.UUID, meeting_id: uuid.UUID, request: MeetingImportComplete
    ) -> Meeting:
        """``uploading → stopped`` once every chunk is on disk — never with a hole."""
        meeting = await self.meetings._owned(meeting_id, user_id, lock=True)
        self._require_uploading(meeting)
        if request.chunk_count > max_import_chunks():
            raise_meeting_too_large(
                "import_too_large", max_bytes=settings.meetings_import_max_bytes
            )
        expected = max(request.chunk_count, meeting.segment_count)
        store = self.meetings.store
        missing = store.missing_sequences(await store.list_sequences(user_id, meeting_id), expected)
        if missing:
            raise_meeting_conflict("segments_missing", missing=missing[:_MISSING_SHOWN])
        # Provisional end: the audio stage writes the real one once ffprobe measured it.
        completed = await self.meetings.repo.stop(
            meeting_id,
            stopped_at=meeting.started_at,
            segment_count=expected,
            accepting=(MeetingStatus.UPLOADING,),
        )
        if not completed:
            raise_meeting_conflict("meeting_not_uploading", status=meeting.status.value)
        meeting_imports_total.labels(format=meeting.audio_format.value, outcome="completed").inc()
        logger.info(
            "meeting_import_completed",
            meeting_id=str(meeting_id),
            chunks=expected,
            audio_bytes=meeting.audio_bytes,
        )
        return await self.meetings._fresh(meeting_id, user_id)

    @staticmethod
    def _require_uploading(meeting: Meeting) -> None:
        if meeting.status is not MeetingStatus.UPLOADING or not is_import(meeting.audio_format):
            raise_meeting_conflict("meeting_not_uploading", status=meeting.status.value)


__all__ = [
    "MeetingImportService",
    "import_limits",
    "import_signature_matches",
    "max_import_chunks",
]
