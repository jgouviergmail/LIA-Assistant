"""Delivery of the minutes: PDF bytes and email from the platform sender (ADR-258, ADR-259).

The email leaves from the platform SMTP sender (``APPLICATION_SMTP_FROM``),
like every account email: the minutes are LIA's document, not a message the
user writes from their mailbox. The body travels as HTML with the Markdown
rendering as the plain-text alternative — the ONE serializer produces both,
so the two parts can never disagree.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.i18n_meetings import get_header_label
from src.domains.document_generation.renderers import render_document
from src.domains.document_generation.schemas import DocumentType
from src.domains.meetings.models import Meeting
from src.domains.meetings.render import (
    build_header,
    minutes_filename_stem,
    render_html,
    render_markdown,
    render_sectioned,
)
from src.domains.meetings.repository import MeetingRepository
from src.domains.meetings.schemas import MeetingReport
from src.infrastructure.email import get_email_service

logger = structlog.get_logger(__name__)

#: Language-neutral separator between the minutes label and the title.
_SUBJECT_SEPARATOR = " · "


class MinutesDeliveryError(Exception):
    """The minutes could not be delivered; ``code`` is a stable, user-facing key."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def render_pdf(meeting: Meeting, report: MeetingReport, *, language: str, gaps: int = 0) -> bytes:
    """The minutes as a PDF (document_generation renderer)."""
    header = build_header(meeting, report, language=language, gaps=gaps)
    content = render_sectioned(report, header, filename_stem=minutes_filename_stem(meeting, report))
    return render_document(DocumentType.PDF, content)


def pdf_filename(meeting: Meeting, report: MeetingReport) -> str:
    """Download name of the PDF."""
    return f"{minutes_filename_stem(meeting, report)}.pdf"


def minutes_subject(report: MeetingReport, language: str) -> str:
    """``<Meeting minutes> · <title>`` — a mailbox lists subjects, not pages."""
    return f"{get_header_label('minutes', language)}{_SUBJECT_SEPARATOR}{report.title}"


async def send_minutes_email(
    db: AsyncSession,
    *,
    user_id: UUID,
    recipient: str,
    meeting: Meeting,
    report: MeetingReport,
    language: str,
    gaps: int = 0,
) -> None:
    """Email the minutes to ``recipient`` from the platform sender and record it.

    Raises:
        MinutesDeliveryError: ``email_send_failed`` when the SMTP relay refused
            or is unreachable (``EmailService`` answers False and logs the cause).
    """
    header = build_header(meeting, report, language=language, gaps=gaps)
    sent = await get_email_service().send_email(
        to_email=recipient,
        subject=minutes_subject(report, language),
        html_body=render_html(report, header),
        text_body=render_markdown(report, header),
    )
    if not sent:
        logger.warning(
            "meeting_minutes_email_failed", meeting_id=str(meeting.id), user_id=str(user_id)
        )
        raise MinutesDeliveryError("email_send_failed", "smtp delivery refused")
    await MeetingRepository(db).set_email_sent(meeting.id, sent_at=datetime.now(UTC))
    logger.info("meeting_minutes_emailed", meeting_id=str(meeting.id), user_id=str(user_id))
