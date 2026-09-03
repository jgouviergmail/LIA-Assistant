"""PDF bytes and the email through the user's connector (ADR-258)."""

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


async def test_email_goes_through_the_resolved_client_and_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SimpleNamespace(send_email=AsyncMock(return_value={"id": "msg"}))
    repo = AsyncMock()
    monkeypatch.setattr(delivery, "_resolve_email_client", AsyncMock(return_value=client))
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
    kwargs = client.send_email.call_args.kwargs
    assert kwargs["to"] == "me@example.org" and kwargs["subject"] == "Point projet"
    assert kwargs["is_html"] is True and "Compte rendu de réunion" in kwargs["body"]
    repo.set_email_sent.assert_awaited_once()


async def test_a_provider_refusal_is_a_delivery_failure_the_user_can_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SimpleNamespace(send_email=AsyncMock(side_effect=RuntimeError("smtp 550")))
    repo = AsyncMock()
    monkeypatch.setattr(delivery, "_resolve_email_client", AsyncMock(return_value=client))
    monkeypatch.setattr(delivery, "MeetingRepository", lambda db: repo)
    with pytest.raises(MinutesDeliveryError) as exc:
        await send_minutes_email(
            AsyncMock(),
            user_id=uuid.uuid4(),
            recipient="me@example.org",
            meeting=_meeting(),
            report=_report(),
            language="fr",
        )
    assert exc.value.code == "email_send_failed"
    repo.set_email_sent.assert_not_awaited()


async def test_no_email_connector_is_its_own_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.domains.connectors.provider_resolver.resolve_active_connector",
        AsyncMock(return_value=None),
    )
    with pytest.raises(MinutesDeliveryError) as exc:
        await delivery._resolve_email_client(uuid.uuid4(), AsyncMock())
    assert exc.value.code == "email_connector_missing"
