"""Bind the exact original dated PDF content, never render during proposal."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.core.i18n import normalize_language
from src.domains.meetings.delivery import pdf_filename
from src.domains.meetings.models import Meeting
from src.domains.meetings.render import build_header
from src.domains.meetings.schemas import MeetingReport
from src.domains.meetings.service import MeetingService, raise_meeting_not_found
from src.infrastructure.file_transfer import LocalFileRead
from src.infrastructure.meeting_pdf import MeetingPDFSnapshot


def pdf_snapshot(
    meeting: Meeting, report: MeetingReport, language: str | None
) -> MeetingPDFSnapshot:
    selected_language = normalize_language(language)
    header = build_header(meeting, report, language=selected_language, gaps=meeting.audio_gaps)
    filename = pdf_filename(meeting, report)
    raw = json.dumps(
        {
            "report": report.model_dump(mode="json"),
            "header": asdict(header),
            "filename": filename,
            "language": selected_language,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return MeetingPDFSnapshot(
        meeting_id=meeting.id,
        title=report.title,
        filename=filename,
        language=selected_language,
        participants_count=len(report.participants),
        sections_count=len(report.sections),
        source_digest=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )


class SavedMeetingPDF:
    async def snapshot(
        self, db: AsyncSession, actor_id: UUID, meeting_id: UUID, language: str | None
    ) -> MeetingPDFSnapshot:
        meeting, report = await MeetingService(db)._ready_with_report(actor_id, meeting_id)
        return pdf_snapshot(meeting, report, language)

    async def render(
        self,
        db: AsyncSession,
        actor_id: UUID,
        expected: MeetingPDFSnapshot,
        check: Callable[[], Awaitable[None]],
    ) -> LocalFileRead:
        service = MeetingService(db)
        if await service.repo.get_for_user(expected.meeting_id, actor_id, lock=True) is None:
            raise_meeting_not_found(expected.meeting_id)
        meeting, report = await service._ready_with_report(actor_id, expected.meeting_id)
        if pdf_snapshot(meeting, report, expected.language) != expected:
            raise ResourceConflictError("meeting_pdf", detail={"error_code": "STALE_STATE"})
        await check()
        content, filename = await service.pdf(
            actor_id, expected.meeting_id, language=expected.language
        )
        await check()
        if filename != expected.filename:
            raise ResourceConflictError("meeting_pdf", detail={"error_code": "STALE_STATE"})
        return LocalFileRead.from_bytes(content)
