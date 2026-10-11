"""SMTP acknowledgment is distinct from later meeting metadata persistence."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.meeting_reports import MeetingReport
from src.domains.meetings.delivery import send_minutes_email
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failure", ["metadata", "lost_ack", "cancelled", "refused", "valid"])
async def test_confirmed_email_never_replays_an_acknowledged_send(failure: str) -> None:
    from src.infrastructure.meeting_email import (
        MeetingEmailCompletionUnknown,
        MeetingEmailConfirmation,
    )

    row = Meeting(
        id=uuid4(),
        user_id=uuid4(),
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        client_timezone="UTC",
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        audio_gaps=0,
    )
    receipt = PreferenceWriteReceipt()
    check = AsyncMock()
    confirmation = MeetingEmailConfirmation(validate=AsyncMock(), check=check, receipt=receipt)
    smtp = AsyncMock(return_value=failure != "refused")
    if failure == "lost_ack":
        smtp.side_effect = TimeoutError()
    if failure == "cancelled":
        smtp.side_effect = asyncio.CancelledError()
    metadata = AsyncMock(side_effect=RuntimeError() if failure == "metadata" else None)
    with (
        patch(
            "src.domains.meetings.delivery.get_email_service",
            return_value=MagicMock(send_email=smtp),
        ),
        patch("src.domains.meetings.delivery.MeetingRepository.set_email_sent", metadata),
    ):
        args = {
            "user_id": row.user_id,
            "recipient": "owner@example.test",
            "meeting": row,
            "report": MeetingReport(title="Controlled"),
            "language": "fr",
            "confirmation": confirmation,
        }
        if failure in {"lost_ack", "cancelled", "refused", "metadata"}:
            with pytest.raises(MeetingEmailCompletionUnknown):
                await send_minutes_email(MagicMock(), **args)
            assert receipt.committed is (failure == "metadata")
            if failure == "metadata":
                assert receipt.values is not None
                assert receipt.values["meeting_email_sent"]["provider_acknowledged"] is True
                assert receipt.values["meeting_email_sent"]["metadata_saved"] is False
            else:
                metadata.assert_not_called()
        else:
            await send_minutes_email(MagicMock(), **args)
            assert receipt.committed and not receipt.no_op
            assert receipt.values is not None
            assert receipt.values["meeting_email_sent"]["provider_acknowledged"] is True
            assert receipt.values["meeting_email_sent"]["recipient_delivery_confirmed"] is False
            assert receipt.values["meeting_email_sent"]["metadata_saved"] is (failure == "valid")
        smtp.assert_awaited_once()
        check.assert_awaited_once()


async def test_late_refusal_sends_nothing() -> None:
    from src.infrastructure.meeting_email import MeetingEmailConfirmation

    check = AsyncMock(side_effect=PermissionError())
    confirmation = MeetingEmailConfirmation(
        validate=AsyncMock(), check=check, receipt=PreferenceWriteReceipt()
    )
    with patch("src.domains.meetings.delivery.get_email_service") as smtp:
        with pytest.raises(PermissionError):
            await send_minutes_email(
                MagicMock(),
                user_id=uuid4(),
                recipient="owner@example.test",
                meeting=Meeting(
                    id=uuid4(), started_at=datetime.now(UTC), client_timezone="UTC", audio_gaps=0
                ),
                report=MeetingReport(title="Controlled"),
                language="fr",
                confirmation=confirmation,
            )
        smtp.assert_not_called()
