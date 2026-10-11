"""Complete transcript/template consent is checked before queuing a rebuild."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, BaseAPIException, ResourceConflictError
from src.core.security.utils import encrypt_data
from src.domains.meetings.models import (
    Meeting,
    MeetingAudioFormat,
    MeetingStage,
    MeetingStatus,
    MeetingTemplate,
)
from src.domains.meetings.service import MeetingService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.confirmed_commit import CommitCompletionUnknown

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "current_changed",
        "transcript_changed",
        "location_changed",
        "late_refusal",
        "lost_ack",
        "running",
        "missing_transcript",
        "template_changed",
    ],
)
async def test_rebuild_consent_is_complete_and_acknowledged(
    async_session: AsyncSession,
    test_user: User,
    scenario: str,
) -> None:
    from src.domains.meetings.regeneration_confirmation import regeneration_snapshot
    from src.infrastructure.meeting_regeneration import MeetingRegenerationConfirmation

    row = Meeting(
        user_id=test_user.id,
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        transcript_encrypted=encrypt_data(
            '[{"speaker":"S1","start":0,"end":1,"text":"Private transcript"}]'
        ),
        report_current={"title": "Original", "participants": [], "sections": []},
        location_label="Approved place",
    )
    async_session.add(row)
    await async_session.commit()
    owner, identity = test_user.id, row.id
    service = MeetingService(async_session)
    if scenario == "template_changed":
        template = MeetingTemplate(
            user_id=owner,
            name="Controlled",
            sections=[
                {
                    "key": "summary",
                    "label": "Summary",
                    "instruction": "Approved instructions",
                    "kind": "paragraph",
                }
            ],
        )
        async_session.add(template)
        await async_session.flush()
        row.template_ref = f"user:{template.id}"
        await async_session.commit()
    expected = await regeneration_snapshot(service, row, test_user)
    if scenario == "template_changed":
        template.sections = [{**template.sections[0], "instruction": "Changed instructions"}]
    if scenario == "current_changed":
        row.report_current = {**row.report_current, "title": "Changed"}
    if scenario == "transcript_changed":
        row.transcript_encrypted = encrypt_data(
            '[{"speaker":"S1","start":0,"end":1,"text":"Different transcript"}]'
        )
    if scenario == "location_changed":
        row.location_label = "Changed place"
    if scenario == "running":
        row.stage = MeetingStage.SYNTHESIZING
    if scenario == "missing_transcript":
        row.transcript_encrypted = None
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
            raise ResourceConflictError(
                "meeting_regeneration", detail={"error_code": "STALE_STATE"}
            )

    confirmation = MeetingRegenerationConfirmation(validate=validate, check=check, receipt=receipt)
    if scenario in {
        "current_changed",
        "transcript_changed",
        "location_changed",
        "template_changed",
    }:
        with pytest.raises(ResourceConflictError):
            await service.regenerate(owner, identity, confirmation=confirmation)
    elif scenario in {"running", "missing_transcript", "late_refusal"}:
        with pytest.raises(BaseAPIException):
            await service.regenerate(owner, identity, confirmation=confirmation)
    elif scenario == "lost_ack":
        original = async_session.commit

        async def commit():
            await original()
            raise OperationalError("COMMIT", {}, Exception("Controlled lost acknowledgment"))

        with patch.object(async_session, "commit", commit):
            with pytest.raises(CommitCompletionUnknown):
                await service.regenerate(owner, identity, confirmation=confirmation)
    else:
        result = await service.regenerate(owner, identity, confirmation=confirmation)
        assert result.status is MeetingStatus.READY and result.stage is MeetingStage.SYNTHESIZING
        assert receipt.committed
        assert receipt.values["meeting_regeneration"]["processing_completed"] is False
    if scenario != "valid":
        assert not receipt.committed
