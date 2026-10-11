"""Original minutes editing, restoration and transcript purge owners."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.core.meeting_reports import apply_report_changes
from src.domains.meetings.models import Meeting, MeetingStatus
from src.domains.meetings.preference_owner import lock_meeting_preference_owner
from src.domains.meetings.report_confirmation import report_state
from src.domains.meetings.repository import LIVE_STATUSES
from src.domains.meetings.schemas import MeetingPatchRequest
from src.domains.meetings.transcript_confirmation import transcript_state
from src.infrastructure.confirmed_commit import commit_confirmed_write
from src.infrastructure.meeting_report_updates import ReportPatchConfirmation
from src.infrastructure.meeting_reports import ReportWriteConfirmation
from src.infrastructure.meeting_transcripts import TranscriptWriteConfirmation

if TYPE_CHECKING:
    from src.domains.meetings.service import MeetingService


async def patch_report(
    service: MeetingService,
    user_id: uuid.UUID,
    meeting_id: uuid.UUID,
    request: MeetingPatchRequest,
    language: str | None = None,
    *,
    confirmation: ReportPatchConfirmation | None = None,
) -> Meeting:
    """Edit the minutes (structured). Re-indexing is the caller's follow-up.

    ``template_ref`` (ADR-259) is accepted only while the meeting is live or
    queued: once processing started the template is the job's, and a READY
    meeting changes format through ``reformat``.
    """
    from src.domains.meetings.service import raise_meeting_conflict, raise_meeting_not_found

    # Template deletion and selection share the same owner-first lock order.
    if request.template_ref is not None:
        await lock_meeting_preference_owner(service.db, user_id)
    meeting = await service.repo.get_for_user(meeting_id, user_id, lock=True)
    if meeting is None:
        raise_meeting_not_found(meeting_id)
    if confirmation is not None:
        from src.domains.meetings.report_patch_confirmation import report_patch_state

        facts = await report_patch_state(service, meeting, request, language)
        await confirmation.check()
        await confirmation.validate(facts)
        # Template definitions are shown as scope; compare only actual saved selection fields.
        desired = {
            key: value
            for key, value in facts.after.items()
            if key != "template_definition_at_confirmation"
        }
        if facts.before == desired:
            await commit_confirmed_write(
                service.db,
                confirmation,
                {
                    "meeting_report_updated": {
                        "meeting_id": str(meeting_id),
                        "saved": True,
                        "indexing_completed": False,
                    }
                },
                no_op=True,
            )
            return await service._fresh(meeting_id, user_id)
    report = service._report_or_none(meeting.report_current)
    if report is None and any(
        value is not None for value in (request.title, request.participants, request.sections)
    ):
        raise_meeting_conflict("report_not_ready", status=meeting.status.value)
    report = apply_report_changes(report, request)
    if request.template_ref is not None:
        await service._apply_template_choice(meeting, request.template_ref, language, commit=False)
        if not request.touches_report:
            await commit_confirmed_write(
                service.db,
                confirmation,
                {
                    "meeting_report_updated": {
                        "meeting_id": str(meeting_id),
                        "saved": True,
                        "indexing_completed": False,
                    }
                },
            )
            return await service._fresh(meeting_id, user_id)
    await service.repo.set_report_current(
        meeting_id,
        report=report.model_dump(mode="json") if report else meeting.report_current,
        edited_at=datetime.now(UTC),
        location_label=request.location_label,
        touch_location=request.location_label is not None,
        commit=False,
    )
    await commit_confirmed_write(
        service.db,
        confirmation,
        {
            "meeting_report_updated": {
                "meeting_id": str(meeting_id),
                "saved": True,
                "indexing_completed": False,
            }
        },
    )
    return await service._fresh(meeting_id, user_id)


async def reset_report(
    service: MeetingService,
    user_id: uuid.UUID,
    meeting_id: uuid.UUID,
    *,
    confirmation: ReportWriteConfirmation | None = None,
) -> Meeting:
    """``report_current ← report_generated`` (the model's version is immutable)."""
    meeting = await service.report_for_restoration(user_id, meeting_id, lock=True)
    state = report_state(meeting)
    if confirmation is not None:
        await confirmation.check()
        await confirmation.validate(state)
    unchanged = confirmation is not None and state.matches_generated
    if not unchanged:
        await service.repo.set_report_current(
            meeting_id,
            report=meeting.report_generated,
            edited_at=datetime.now(UTC),
            location_label=None,
            touch_location=False,
            commit=False,
        )
    await commit_confirmed_write(
        service.db,
        confirmation,
        {
            "meeting_report_restored": {
                "meeting_id": str(meeting_id),
                "restored": True,
                "indexing_completed": False,
            }
        },
        no_op=unchanged,
    )
    return await service._fresh(meeting_id, user_id)


async def report_for_restoration(
    service: MeetingService, user_id: uuid.UUID, meeting_id: uuid.UUID, *, lock: bool = False
) -> Meeting:
    """One owned generated-version availability rule for preview and restore."""
    from src.domains.meetings.service import raise_meeting_conflict, raise_meeting_not_found

    meeting = await service.repo.get_for_user(meeting_id, user_id, lock=lock)
    if meeting is None:
        raise_meeting_not_found(meeting_id)
    if not meeting.report_generated:
        raise_meeting_conflict("report_not_ready", status=meeting.status.value)
    return meeting


async def delete_transcript(
    service: MeetingService,
    user_id: uuid.UUID,
    meeting_id: uuid.UUID,
    *,
    confirmation: TranscriptWriteConfirmation | None = None,
) -> Meeting:
    """Purge the transcript, keep the minutes."""
    meeting = await service.transcript_for_deletion(user_id, meeting_id, lock=True)
    state = transcript_state(meeting)
    if confirmation is not None:
        await confirmation.check()
        await confirmation.validate(state)
    unchanged = confirmation is not None and not state.has_transcript
    if not unchanged:
        await service.repo.delete_transcript(meeting_id, deleted_at=datetime.now(UTC), commit=False)
    await commit_confirmed_write(
        service.db,
        confirmation,
        {
            "meeting_transcript_deleted": {
                "meeting_id": str(meeting_id),
                "deleted": True,
                "minutes_preserved": True,
            }
        },
        no_op=unchanged,
    )
    return await service._fresh(meeting_id, user_id)


async def transcript_for_deletion(
    service: MeetingService, user_id: uuid.UUID, meeting_id: uuid.UUID, *, lock: bool = False
) -> Meeting:
    """One original ownership/status rule for preview and confirmed purge."""
    from src.domains.meetings.service import raise_meeting_conflict, raise_meeting_not_found

    meeting = await service.repo.get_for_user(meeting_id, user_id, lock=lock)
    if meeting is None:
        raise_meeting_not_found(meeting_id)
    if meeting.status in LIVE_STATUSES or meeting.status is MeetingStatus.PROCESSING:
        raise_meeting_conflict("meeting_in_progress", status=meeting.status.value)
    return meeting
