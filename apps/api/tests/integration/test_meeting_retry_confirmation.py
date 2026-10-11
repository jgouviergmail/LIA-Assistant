"""Full retry consent refuses changed bytes before resetting the job budget."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.meetings.service import MeetingService
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
        "removed_audio",
        "foreign_path",
        "late_refusal",
        "lost_ack",
        "transition_refused",
    ],
)
async def test_original_retry_seals_content_and_commit_ack(
    async_session: AsyncSession,
    test_user: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    from src.domains.meetings.retry_confirmation import retry_snapshot
    from src.infrastructure.meeting_retry import MeetingRetryConfirmation

    monkeypatch.setattr(settings, "meetings_storage_path", str(tmp_path))
    row = Meeting(
        user_id=test_user.id,
        status=MeetingStatus.FAILED,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        attempts=3,
        report_current={"title": "Current", "participants": [], "sections": []},
    )
    async_session.add(row)
    await async_session.commit()
    owner, identity = test_user.id, row.id
    service = MeetingService(async_session)
    await service.store.write_segment(owner, identity, 0, b"old-audio")
    expected = await retry_snapshot(service, row, test_user)
    if scenario == "body_changed":
        row.report_current = {**row.report_current, "title": "Changed"}
    if scenario == "audio_changed":
        await service.store.write_segment(owner, identity, 0, b"new-audio")
    if scenario == "removed_audio":
        await service.store.purge_meeting(owner, identity)
    if scenario == "foreign_path":
        row.audio_path = "someone-else/private.webm"
    await async_session.commit()
    receipt = PreferenceWriteReceipt()
    checks = 0

    async def check() -> None:
        nonlocal checks
        checks += 1
        if scenario == "late_refusal" and checks == 2:
            raise AuthorizationError(detail={"error_code": "CAPABILITY_DISABLED"})

    async def validate(actual) -> None:
        if actual != expected:
            raise ResourceConflictError("meeting_retry", detail={"error_code": "STALE_STATE"})

    confirmation = MeetingRetryConfirmation(validate=validate, check=check, receipt=receipt)
    if scenario in {"body_changed", "audio_changed", "foreign_path"}:
        with pytest.raises((ResourceConflictError, RuntimeError)):
            await service.retry(owner, identity, confirmation=confirmation)
    elif scenario == "removed_audio":
        from src.core.exceptions import BaseAPIException

        with pytest.raises(BaseAPIException):
            await service.retry(owner, identity, confirmation=confirmation)
    elif scenario == "late_refusal":
        with pytest.raises(AuthorizationError):
            await service.retry(owner, identity, confirmation=confirmation)
    elif scenario == "transition_refused":
        with patch.object(service.repo, "requeue_for_retry", return_value=False):
            from src.core.exceptions import BaseAPIException

            with pytest.raises(BaseAPIException):
                await service.retry(owner, identity, confirmation=confirmation)
    elif scenario == "lost_ack":
        original = async_session.commit

        async def commit() -> None:
            await original()
            raise OperationalError("COMMIT", {}, Exception("Controlled lost acknowledgment"))

        with patch.object(async_session, "commit", commit):
            with pytest.raises(CommitCompletionUnknown):
                await service.retry(owner, identity, confirmation=confirmation)
    else:
        result = await service.retry(owner, identity, confirmation=confirmation)
        assert result.status is MeetingStatus.STOPPED
        assert result.attempts == 0
        assert receipt.committed
        assert receipt.values["meeting_retry"]["processing_completed"] is False
    if scenario != "valid":
        assert not receipt.committed
