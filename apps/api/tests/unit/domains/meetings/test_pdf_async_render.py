"""Rendering minutes must leave the event loop free to serve other requests."""

import asyncio
from threading import Event, get_ident
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.meetings.service import MeetingService

pytestmark = pytest.mark.unit


async def test_pdf_header_reads_stay_in_the_request_task() -> None:
    from datetime import UTC, datetime

    from src.core.meeting_reports import MeetingReport
    from src.domains.meetings import delivery
    from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus

    owner_thread = get_ident()
    seen: list[int] = []
    real_header = delivery.build_header

    def header(*args, **kwargs):
        seen.append(get_ident())
        return real_header(*args, **kwargs)

    row = Meeting(
        id=uuid4(),
        user_id=uuid4(),
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        audio_gaps=0,
    )
    service = MeetingService(MagicMock())
    service._ready_with_report = AsyncMock(return_value=(row, MeetingReport(title="Controlled")))
    with (
        patch("src.domains.meetings.delivery.build_header", header),
        patch("src.domains.meetings.delivery.render_document", return_value=b"%PDF-controlled"),
    ):
        await service.pdf(row.user_id, row.id, language="fr")
    assert seen == [owner_thread]


async def test_pdf_renderer_does_not_block_other_requests() -> None:
    from datetime import UTC, datetime

    from src.core.meeting_reports import MeetingReport
    from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus

    release = Event()

    def render(*args, **kwargs):
        assert release.wait(timeout=2), "The event loop was blocked by PDF rendering"
        return b"%PDF-controlled"

    service = MeetingService(MagicMock())
    row = Meeting(
        id=uuid4(),
        user_id=uuid4(),
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        audio_gaps=0,
    )
    service._ready_with_report = AsyncMock(return_value=(row, MeetingReport(title="Controlled")))

    async def heartbeat() -> None:
        await asyncio.sleep(0.01)
        release.set()

    with (
        patch("src.domains.meetings.delivery.render_document", render),
        patch("src.domains.meetings.service.pdf_filename", return_value="minutes.pdf"),
    ):
        pdf, _ = await asyncio.gather(service.pdf(uuid4(), uuid4(), language="fr"), heartbeat())
    assert pdf == (b"%PDF-controlled", "minutes.pdf")
