"""Both original reformat modes obey complete consent and known commit receipts."""

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select
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


@pytest.mark.parametrize("mode", ["replace", "new"])
@pytest.mark.parametrize(
    "scenario",
    ["valid", "template_changed", "transcript_changed", "late_refusal", "lost_ack", "source_busy"],
)
async def test_reformat_validates_original_source_and_template_before_atomic_write(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    scenario: str,
) -> None:
    from src.core.meeting_reformat import MeetingReformatRequest
    from src.domains.meetings.reformat import reformat_meeting
    from src.domains.meetings.reformat_confirmation import reformat_snapshot
    from src.infrastructure.meeting_reformat import MeetingReformatConfirmation

    row = Meeting(
        user_id=test_user.id,
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        transcript_encrypted=encrypt_data(
            '[{"speaker":"S1","start":0,"end":1,"text":"Private transcript"}]'
        ),
        report_current={"title": "Current", "participants": [], "sections": []},
    )
    template = MeetingTemplate(
        user_id=test_user.id,
        name="Selected",
        sections=[
            {
                "key": "summary",
                "label": "Summary",
                "instruction": "Original instruction",
                "kind": "paragraph",
            }
        ],
    )
    if scenario == "source_busy":
        row.stage = MeetingStage.SYNTHESIZING
    async_session.add_all([row, template])
    await async_session.commit()
    owner, identity, target = test_user.id, row.id, uuid4()
    request = MeetingReformatRequest(template_ref=f"user:{template.id}", mode=mode)
    service = MeetingService(async_session)
    if scenario == "source_busy" and mode == "replace":
        with pytest.raises(BaseAPIException):
            await reformat_snapshot(service, row, test_user, request, destination_id=identity)
        return
    expected = await reformat_snapshot(
        service, row, test_user, request, destination_id=target if mode == "new" else identity
    )
    if scenario == "template_changed":
        template.sections = [{**template.sections[0], "instruction": "Changed instruction"}]
    if scenario == "transcript_changed":
        row.transcript_encrypted = encrypt_data(
            '[{"speaker":"S1","start":0,"end":1,"text":"Different"}]'
        )
    await async_session.commit()
    receipt = PreferenceWriteReceipt()
    checks = 0

    async def check() -> None:
        nonlocal checks
        checks += 1
        if scenario == "late_refusal" and checks == 2:
            raise AuthorizationError(detail={"error_code": "FORBIDDEN"})

    async def validate(actual) -> None:
        if actual != expected:
            raise ResourceConflictError("meeting_reformat", detail={"error_code": "STALE_STATE"})

    if scenario == "lost_ack":
        original_commit = async_session.commit

        async def lost_commit() -> None:
            monkeypatch.setattr(async_session, "commit", original_commit)
            await original_commit()
            raise OperationalError("COMMIT", {}, Exception("Controlled lost acknowledgment"))

        monkeypatch.setattr(async_session, "commit", lost_commit)

    confirmation = MeetingReformatConfirmation(
        validate=validate, check=check, receipt=receipt, destination_id=expected.destination_id
    )
    with patch("src.domains.meetings.reformat.launch_regenerate") as launch:
        if scenario in {"valid", "source_busy"}:
            result = await reformat_meeting(
                service, owner, identity, request, "fr", confirmation=confirmation
            )
            assert result.id == expected.destination_id and receipt.committed
            assert receipt.values["meeting_reformat"]["processing_completed"] is False
        else:
            error = (
                CommitCompletionUnknown
                if scenario == "lost_ack"
                else (AuthorizationError if scenario == "late_refusal" else ResourceConflictError)
            )
            with pytest.raises(error):
                await reformat_meeting(
                    service, owner, identity, request, "fr", confirmation=confirmation
                )
            assert not receipt.committed
            if scenario != "lost_ack":
                await async_session.rollback()
        launch.assert_not_called()
    derived = await async_session.scalar(select(Meeting).where(Meeting.id == target))
    assert (derived is not None) is (
        mode == "new" and scenario in {"valid", "lost_ack", "source_busy"}
    )
    if derived is not None:
        assert derived.source_meeting_id == identity
        assert derived.audio_path is None and derived.stt_cost_eur is None
    await async_session.refresh(row)
    assert (row.stage is not None) is (
        (mode == "replace" and scenario in {"valid", "lost_ack"}) or scenario == "source_busy"
    )
