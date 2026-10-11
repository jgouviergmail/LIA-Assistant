"""The original transcript writer must honor fresh consent before purging."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.exceptions import ResourceConflictError
from src.domains.meetings.models import MeetingStatus
from src.domains.meetings.service import MeetingService
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.unit


async def test_changed_transcript_refuses_the_original_purge_before_sql() -> None:
    from src.infrastructure.meeting_transcripts import TranscriptWriteConfirmation

    service = MeetingService(MagicMock())
    service.repo = AsyncMock()
    service.repo.get_for_user.return_value = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        status=MeetingStatus.READY,
        stage=None,
        transcript_encrypted="private-ciphertext",
        transcript_deleted_at=None,
        report_current={"title": "Controlled"},
    )
    receipt = PreferenceWriteReceipt()
    confirmation = TranscriptWriteConfirmation(
        validate=AsyncMock(
            side_effect=ResourceConflictError(
                "meeting_transcript", detail={"error_code": "STALE_STATE"}
            )
        ),
        check=AsyncMock(),
        receipt=receipt,
    )
    row = service.repo.get_for_user.return_value
    with pytest.raises(ResourceConflictError):
        await service.delete_transcript(row.user_id, row.id, confirmation=confirmation)
    service.repo.delete_transcript.assert_not_awaited()
    assert not receipt.committed


async def test_cancelled_commit_has_no_success_receipt() -> None:
    import asyncio

    from src.infrastructure.confirmed_commit import CommitCompletionUnknown, commit_confirmed_write
    from src.infrastructure.meeting_transcripts import TranscriptWriteConfirmation

    db = MagicMock()
    db.commit = AsyncMock(side_effect=asyncio.CancelledError())
    receipt = PreferenceWriteReceipt()
    confirmation = TranscriptWriteConfirmation(
        validate=AsyncMock(), check=AsyncMock(), receipt=receipt
    )
    with pytest.raises(CommitCompletionUnknown):
        await commit_confirmed_write(db, confirmation, {})
    assert not receipt.committed and receipt.values is None
