"""PDF bytes and the email from the platform SMTP sender (ADR-258, ADR-259)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.domains.meetings import delivery
from src.domains.meetings.delivery import (
    MinutesDeliveryError,
    pdf_filename,
    render_pdf,
    send_minutes_email,
)
from src.domains.meetings.schemas import MeetingReport, ReportSection, SectionKind

pytestmark = pytest.mark.unit


def _meeting() -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        client_timezone="Europe/Paris",
        started_at=datetime(2026, 9, 2, 8, 0, tzinfo=UTC),
        stopped_at=datetime(2026, 9, 2, 9, 0, tzinfo=UTC),
        audio_duration_seconds=3600.0,
        location_label=None,
    )


def _report() -> MeetingReport:
    return MeetingReport(
        title="Point projet",
        sections=[
            ReportSection(
                key="summary", label="Résumé", kind=SectionKind.PARAGRAPH, paragraph="Ok."
            )
        ],
    )


def test_render_pdf_produces_a_pdf_named_after_the_meeting() -> None:
    meeting = _meeting()
    pdf = render_pdf(meeting, _report(), language="fr")
    assert pdf.startswith(b"%PDF")
    assert pdf_filename(meeting, _report()) == "2026-09-02 Point projet.pdf"


async def test_email_goes_through_the_platform_smtp_service_and_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = SimpleNamespace(send_email=AsyncMock(return_value=True))
    repo = AsyncMock()
    monkeypatch.setattr(delivery, "get_email_service", lambda: sender)
    monkeypatch.setattr(delivery, "MeetingRepository", lambda db: repo)
    meeting = _meeting()
    await send_minutes_email(
        AsyncMock(),
        user_id=uuid.uuid4(),
        recipient="me@example.org",
        meeting=meeting,
        report=_report(),
        language="fr",
        gaps=0,
    )
    kwargs = sender.send_email.await_args.kwargs
    assert kwargs["to_email"] == "me@example.org"
    assert kwargs["subject"] == "Compte rendu de réunion · Point projet"
    assert "<h1" in kwargs["html_body"] and "Compte rendu de réunion" in kwargs["html_body"]
    # multipart/alternative for free: the ONE serializer already produces the text side
    assert kwargs["text_body"].startswith("# Point projet")
    repo.set_email_sent.assert_awaited_once()


async def test_a_refused_delivery_is_email_send_failed_and_nothing_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = SimpleNamespace(send_email=AsyncMock(return_value=False))
    repo = AsyncMock()
    monkeypatch.setattr(delivery, "get_email_service", lambda: sender)
    monkeypatch.setattr(delivery, "MeetingRepository", lambda db: repo)
    with pytest.raises(MinutesDeliveryError) as exc:
        await send_minutes_email(
            AsyncMock(),
            user_id=uuid.uuid4(),
            recipient="me@example.org",
            meeting=_meeting(),
            report=_report(),
            language="en",
        )
    assert exc.value.code == "email_send_failed"
    repo.set_email_sent.assert_not_awaited()


def test_the_subject_is_localized_and_names_the_meeting() -> None:
    assert delivery.minutes_subject(_report(), "en") == "Meeting minutes · Point projet"
    assert delivery.minutes_subject(_report(), "zh") == "会议纪要 · Point projet"
