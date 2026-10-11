"""Exact delete confirmation guards complete source and known cleanup acknowledgment."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.core.security.utils import encrypt_data
from src.domains.meetings.audio_store import MeetingAudioStore
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.meetings.service import MeetingService
from src.domains.rag_spaces.models import RAGDocument, RAGSpace
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.confirmed_commit import CommitCompletionUnknown

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "body_changed",
        "audio_changed",
        "late_refusal",
        "lost_ack",
        "cleanup_failed",
        "no_transcript",
        "corrupt_transcript",
        "orphaned_audio",
        "projection_changed",
    ],
)
async def test_meeting_delete_seals_full_data_and_reports_cleanup_truthfully(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
) -> None:
    from src.domains.meetings.deletion_confirmation import deletion_snapshot
    from src.infrastructure.meeting_deletions import MeetingDeletionConfirmation

    monkeypatch.setattr(settings, "meetings_storage_path", str(tmp_path))
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path / "rag"))
    row = Meeting(
        user_id=test_user.id,
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        report_current={"title": "Current", "participants": [], "sections": []},
        transcript_encrypted=encrypt_data('[{"speaker":"S1","start":0,"end":1,"text":"Private"}]'),
    )
    if scenario == "no_transcript":
        row.transcript_encrypted = None
    if scenario == "corrupt_transcript":
        row.transcript_encrypted = "invalid encrypted content"
    async_session.add(row)
    if scenario == "projection_changed":
        space = RAGSpace(user_id=test_user.id, name="Controlled projection", kind="meetings")
        async_session.add(space)
        await async_session.flush()
        document = RAGDocument(
            user_id=test_user.id,
            space_id=space.id,
            filename="minutes.md",
            original_filename="Minutes",
            file_size=4,
            content_type="text/markdown",
            status="ready",
            source_type="meeting",
        )
        async_session.add(document)
        await async_session.flush()
        row.rag_document_id = document.id
    await async_session.commit()
    owner, identity = test_user.id, row.id
    store = MeetingAudioStore(tmp_path)
    await store.write_segment(owner, identity, 0, b"approved-audio")
    if scenario == "orphaned_audio":
        (store.meeting_dir(owner, identity) / "audio.webm").write_bytes(b"other-recorded-audio")
    service = MeetingService(async_session)
    expected = await deletion_snapshot(service, row)
    if scenario == "projection_changed":
        await async_session.execute(
            update(RAGDocument)
            .where(RAGDocument.id == document.id)
            .values(file_size=5)
            .execution_options(synchronize_session=False)
        )
        await async_session.commit()
    if scenario == "orphaned_audio":
        assert expected.audio_files == 2
    if scenario == "body_changed":
        row.report_current = {"title": "Edited", "participants": [], "sections": []}
        await async_session.commit()
    if scenario == "audio_changed":
        await store.write_segment(owner, identity, 0, b"changed--audio")
    receipt = PreferenceWriteReceipt()
    checks = 0

    async def check() -> None:
        nonlocal checks
        checks += 1
        if scenario == "late_refusal" and checks == 2:
            raise AuthorizationError(detail={"error_code": "FORBIDDEN"})

    async def validate(actual) -> None:
        if actual != expected:
            raise ResourceConflictError("meeting_delete", detail={"error_code": "STALE_STATE"})

    if scenario == "lost_ack":
        original_commit = async_session.commit

        async def lost_commit() -> None:
            monkeypatch.setattr(async_session, "commit", original_commit)
            await original_commit()
            raise OperationalError("COMMIT", {}, Exception("Controlled lost acknowledgment"))

        monkeypatch.setattr(async_session, "commit", lost_commit)
    if scenario == "cleanup_failed":
        monkeypatch.setattr(service.store, "purge_meeting", AsyncMock(return_value=False))
    confirmation = MeetingDeletionConfirmation(validate=validate, check=check, receipt=receipt)
    successful = {
        "valid",
        "cleanup_failed",
        "no_transcript",
        "corrupt_transcript",
        "orphaned_audio",
    }
    if scenario in successful:
        await service.delete(owner, identity, confirmation=confirmation)
        assert receipt.committed and receipt.values["meeting_delete"]["database_deleted"] is True
        assert receipt.values["meeting_delete"]["files_cleanup_completed"] is (
            scenario != "cleanup_failed"
        )
    else:
        error = (
            CommitCompletionUnknown
            if scenario == "lost_ack"
            else (AuthorizationError if scenario == "late_refusal" else ResourceConflictError)
        )
        with pytest.raises(error):
            await service.delete(owner, identity, confirmation=confirmation)
        assert not receipt.committed
        if scenario != "lost_ack":
            await async_session.rollback()
    assert (await async_session.get(Meeting, identity, populate_existing=True) is None) is (
        scenario in successful | {"lost_ack"}
    )
    assert store.meeting_dir(owner, identity).exists() is (
        scenario not in successful - {"cleanup_failed"}
    )
