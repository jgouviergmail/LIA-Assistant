"""Restoring generated minutes must refuse a changed full report before writing."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.meetings.service import MeetingService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.confirmed_commit import CommitCompletionUnknown

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention",
    ["none", "generated_changed", "current_changed", "no_op", "late_refusal", "lost_ack"],
)
async def test_original_restore_is_full_state_cas_and_preserves_location(
    async_session: AsyncSession, test_user: User, intervention: str
) -> None:
    from src.domains.meetings.report_confirmation import report_state
    from src.infrastructure.meeting_reports import MeetingReportState, ReportWriteConfirmation

    current = {"title": "Edited", "participants": [], "sections": []}
    generated = {"title": "Generated", "participants": [], "sections": []}
    if intervention == "no_op":
        current = dict(generated)
    row = Meeting(
        user_id=test_user.id,
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        report_current=current,
        report_generated=generated,
        location_label="Preserved location",
    )
    async_session.add(row)
    await async_session.commit()
    actor_id, meeting_id = test_user.id, row.id
    expected = report_state(row)
    receipt = PreferenceWriteReceipt()

    checks = 0

    async def check() -> None:
        nonlocal checks
        checks += 1
        if intervention == "late_refusal" and checks == 2:
            raise AuthorizationError(detail={"error_code": "CAPABILITY_DISABLED"})

    async def validate(actual: MeetingReportState) -> None:
        if actual != expected:
            raise ResourceConflictError("meeting_report", detail={"error_code": "STALE_STATE"})

    changed = intervention in {"generated_changed", "current_changed"}
    if intervention == "generated_changed":
        row.report_generated = {**generated, "title": "Changed generation"}
        await async_session.commit()
    if intervention == "current_changed":
        current = {**current, "title": "Changed edit"}
        row.report_current = current
        await async_session.commit()
    confirmation = ReportWriteConfirmation(validate=validate, check=check, receipt=receipt)
    if changed or intervention == "late_refusal":
        with pytest.raises(ResourceConflictError if changed else AuthorizationError):
            await MeetingService(async_session).reset_report(
                actor_id, meeting_id, confirmation=confirmation
            )
        await async_session.rollback()
    elif intervention == "lost_ack":
        real_commit = async_session.commit

        async def lost_commit() -> None:
            await real_commit()
            raise OperationalError("COMMIT", {}, Exception("lost acknowledgment"))

        with (
            patch.object(async_session, "commit", lost_commit),
            pytest.raises(CommitCompletionUnknown),
        ):
            await MeetingService(async_session).reset_report(
                actor_id, meeting_id, confirmation=confirmation
            )
    else:
        await MeetingService(async_session).reset_report(
            actor_id, meeting_id, confirmation=confirmation
        )
    await async_session.refresh(row)
    assert row.report_current == (
        current if changed or intervention == "late_refusal" else generated
    )
    assert row.location_label == "Preserved location"
    assert receipt.committed is (intervention in {"none", "no_op"})
    assert receipt.no_op is (intervention == "no_op")
