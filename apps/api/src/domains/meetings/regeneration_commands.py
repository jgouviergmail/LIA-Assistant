"""The original rebuild queue owner gains optional exact confirmation."""

from typing import TYPE_CHECKING
from uuid import UUID

from src.domains.meetings.models import Meeting, MeetingStatus
from src.domains.meetings.regeneration_confirmation import regeneration_snapshot
from src.domains.users.repository import UserRepository
from src.infrastructure.confirmed_commit import commit_confirmed_write
from src.infrastructure.meeting_regeneration import MeetingRegenerationConfirmation

if TYPE_CHECKING:
    from src.domains.meetings.service import MeetingService


async def queue_regeneration(
    service: MeetingService,
    user_id: UUID,
    meeting_id: UUID,
    confirmation: MeetingRegenerationConfirmation | None,
) -> Meeting:
    from src.domains.meetings.service import raise_meeting_conflict, raise_meeting_not_found

    if confirmation is not None:
        actor = await UserRepository(service.db).get_by_id_for_preference_update(user_id)
        meeting = await service.repo.get_for_user(meeting_id, user_id, lock=True)
        if actor is None or meeting is None:
            raise_meeting_not_found(meeting_id)
        await confirmation.validate(await regeneration_snapshot(service, meeting, actor))
        await confirmation.check()
    else:
        meeting = await service._owned(meeting_id, user_id)
        if meeting.status is not MeetingStatus.READY:
            raise_meeting_conflict("report_not_ready", status=meeting.status.value)
        if not meeting.transcript_encrypted:
            raise_meeting_conflict("transcript_unavailable")
    if not await service.repo.begin_regenerate(meeting_id, commit=False):
        raise_meeting_conflict("regeneration_in_progress")
    await commit_confirmed_write(
        service.db,
        confirmation,
        {
            "meeting_regeneration": {
                "meeting_id": str(meeting_id),
                "status": "ready",
                "stage": "synthesizing",
                "processing_completed": False,
                "indexing_completed": False,
            }
        },
    )
    return await service._fresh(meeting_id, user_id)
