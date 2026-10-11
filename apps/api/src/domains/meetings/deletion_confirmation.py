"""Seal complete original meeting, audio and owned projection before deletion."""

import hashlib
import json
from contextlib import suppress
from typing import TYPE_CHECKING

from pydantic import ValidationError
from sqlalchemy import select

from src.domains.meetings.models import Meeting, MeetingStatus
from src.domains.meetings.repository import LIVE_STATUSES
from src.domains.meetings.retry_audio import seal_meeting_directory
from src.domains.rag_spaces.document_access import document_file_path
from src.domains.rag_spaces.models import RAGDocument
from src.infrastructure.file_transfer import LocalFileRead
from src.infrastructure.meeting_deletions import MeetingDeletionSnapshot

if TYPE_CHECKING:
    from src.domains.meetings.service import MeetingService


async def deletion_projection(
    service: MeetingService,
    meeting: Meeting,
    *,
    lock: bool = False,
) -> tuple[dict[str, object], bool]:
    from src.domains.meetings.service import raise_meeting_not_found

    if meeting.rag_document_id is None:
        return {}, False
    query = (
        select(RAGDocument)
        .where(RAGDocument.id == meeting.rag_document_id)
        .execution_options(populate_existing=True)
    )
    document = await service.db.scalar(query.with_for_update() if lock else query)
    if document is None:
        return {}, False
    if document.user_id != meeting.user_id or document.source_type != "meeting":
        raise_meeting_not_found(meeting.id)
    digest = None
    with suppress(FileNotFoundError):
        reader = LocalFileRead.open(document_file_path(document))
        try:
            digest = reader.identity_digest
        finally:
            await reader.close()
    return {
        "row": {
            column.key: getattr(document, column.key) for column in RAGDocument.__table__.columns
        },
        "file_digest": digest,
    }, True


async def deletion_snapshot(
    service: MeetingService,
    meeting: Meeting,
    *,
    lock_projection: bool = False,
) -> MeetingDeletionSnapshot:
    from src.domains.meetings.service import raise_meeting_conflict, worker_stale

    if meeting.status in LIVE_STATUSES:
        raise_meeting_conflict("meeting_in_progress", status=meeting.status.value)
    if meeting.status is MeetingStatus.PROCESSING and not worker_stale(meeting):
        raise_meeting_conflict("meeting_in_progress", status=meeting.status.value)
    report = None
    with suppress(ValidationError):
        report = service._report_or_none(meeting.report_current)
    audio = await seal_meeting_directory(service.store, meeting.user_id, meeting.id)
    projection, present = await deletion_projection(service, meeting, lock=lock_projection)
    raw = json.dumps(
        {
            "meeting": {
                column.key: getattr(meeting, column.key) for column in Meeting.__table__.columns
            },
            "audio": audio.digest,
            "projection": projection,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return MeetingDeletionSnapshot(
        meeting_id=meeting.id,
        status=meeting.status.value,
        stage=meeting.stage.value if meeting.stage is not None else None,
        title=report.title if report else None,
        current_valid=meeting.report_current is None or report is not None,
        current_sections_count=len(report.sections) if report else None,
        generated_report_present=meeting.report_generated is not None,
        transcript_present=bool(meeting.transcript_encrypted),
        audio_files=audio.files,
        audio_bytes_on_disk=audio.bytes_on_disk,
        projection_id=meeting.rag_document_id,
        projection_present=present,
        derived_minutes_kept=await service.repo.count_derived(meeting.id),
        source_digest=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )
