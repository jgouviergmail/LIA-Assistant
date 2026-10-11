"""Confirmed purges run on the original PostgreSQL writer and preserve minutes."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.core.security.utils import encrypt_data
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.meetings.service import MeetingService
from src.domains.meetings.transcript_confirmation import transcript_state
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.confirmed_commit import CommitCompletionUnknown
from src.infrastructure.meeting_transcripts import (
    MeetingTranscriptState,
    TranscriptWriteConfirmation,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("intervention", ["none", "changed", "late_refusal", "no_op", "lost_ack"])
async def test_original_purge_checks_fresh_facts_and_commit_ack(
    async_session: AsyncSession, test_user: User, intervention: str
) -> None:
    report = {"title": "Preserved minutes", "participants": [], "sections": []}
    row = Meeting(
        user_id=test_user.id,
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        report_current=report,
        transcript_encrypted=(
            None if intervention == "no_op" else encrypt_data("private transcript")
        ),
    )
    async_session.add(row)
    await async_session.commit()
    actor_id, meeting_id = test_user.id, row.id
    expected = transcript_state(row)
    receipt = PreferenceWriteReceipt()
    checks = 0

    async def check() -> None:
        nonlocal checks
        checks += 1
        if intervention == "late_refusal" and checks == 2:
            raise AuthorizationError(detail={"error_code": "CAPABILITY_DISABLED"})

    async def validate(actual: MeetingTranscriptState) -> None:
        if actual != expected:
            raise ResourceConflictError("meeting_transcript", detail={"error_code": "STALE_STATE"})

    if intervention == "changed":
        row.transcript_encrypted = encrypt_data("changed transcript")
        await async_session.commit()
    service = MeetingService(async_session)
    confirmation = TranscriptWriteConfirmation(validate=validate, check=check, receipt=receipt)
    if intervention == "lost_ack":
        real_commit = async_session.commit

        async def commit_lost() -> None:
            await real_commit()
            raise OperationalError("COMMIT", {}, Exception("lost acknowledgment"))

        with (
            patch.object(async_session, "commit", commit_lost),
            pytest.raises(CommitCompletionUnknown),
        ):
            await service.delete_transcript(actor_id, meeting_id, confirmation=confirmation)
    elif intervention in {"changed", "late_refusal"}:
        with pytest.raises(
            ResourceConflictError if intervention == "changed" else AuthorizationError
        ):
            await service.delete_transcript(actor_id, meeting_id, confirmation=confirmation)
        await async_session.rollback()
    else:
        await service.delete_transcript(actor_id, meeting_id, confirmation=confirmation)
    await async_session.refresh(row)
    assert row.report_current == report
    if intervention in {"changed", "late_refusal"}:
        assert row.transcript_encrypted is not None
    else:
        assert row.transcript_encrypted is None
    assert receipt.committed is (intervention in {"none", "no_op"})
    assert receipt.no_op is (intervention == "no_op")
