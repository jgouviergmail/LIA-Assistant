"""Delivery of the minutes: PDF bytes and email through the user's connector (ADR-258).

The email goes through the user's ACTIVE email connector (Google, Microsoft or
Apple), resolved exactly like the telephony availability pre-fetch resolves the
calendar: provider resolver → credentials → client class from the registry. The
minutes travel as the HTML body — the connector protocol has no attachment
seam, and a body reads on every phone without a download.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.document_generation.renderers import render_document
from src.domains.document_generation.schemas import DocumentType
from src.domains.meetings.models import Meeting
from src.domains.meetings.render import (
    build_header,
    minutes_filename_stem,
    render_html,
    render_sectioned,
)
from src.domains.meetings.repository import MeetingRepository
from src.domains.meetings.schemas import MeetingReport

logger = structlog.get_logger(__name__)


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


async def _resolve_email_client(user_id: UUID, db: AsyncSession) -> Any:
    """The user's active email client, or raise ``email_connector_missing``."""
    from src.domains.connectors.clients.registry import ClientRegistry
    from src.domains.connectors.provider_resolver import resolve_active_connector
    from src.domains.connectors.service import ConnectorService

    connector_service = ConnectorService(db)
    resolved_type = await resolve_active_connector(user_id, "email", connector_service)
    if resolved_type is None:
        raise MinutesDeliveryError("email_connector_missing", "no active email connector")
    credentials = (
        await connector_service.get_apple_credentials(user_id, resolved_type)
        if resolved_type.is_apple
        else await connector_service.get_connector_credentials(user_id, resolved_type)
    )
    if not credentials:
        raise MinutesDeliveryError("email_connector_missing", "email connector has no credentials")
    client_class = ClientRegistry.get_client_class(resolved_type)
    if client_class is None:
        raise MinutesDeliveryError("email_connector_missing", "no client for the email connector")
    return client_class(user_id, credentials, connector_service)


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
    """Email the minutes to ``recipient`` (the user's own address) and record it.

    Raises:
        MinutesDeliveryError: ``email_connector_missing`` when no active email
            connector can send, ``email_send_failed`` when the provider refused.
    """
    client = await _resolve_email_client(user_id, db)
    header = build_header(meeting, report, language=language, gaps=gaps)
    body = render_html(report, header)
    try:
        await client.send_email(to=recipient, subject=report.title, body=body, is_html=True)
    except Exception as exc:  # noqa: BLE001 — three provider clients, three exception zoos
        logger.warning(
            "meeting_minutes_email_failed",
            meeting_id=str(meeting.id),
            user_id=str(user_id),
            error=exc.__class__.__name__,
        )
        raise MinutesDeliveryError("email_send_failed", str(exc)) from exc
    await MeetingRepository(db).set_email_sent(meeting.id, sent_at=datetime.now(UTC))
    logger.info("meeting_minutes_emailed", meeting_id=str(meeting.id), user_id=str(user_id))
