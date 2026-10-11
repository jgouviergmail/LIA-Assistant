"""The existing retry transaction gains optional exact human-consent checks."""

from typing import TYPE_CHECKING
from uuid import UUID

from src.domains.meetings.models import Meeting, MeetingStatus
from src.domains.meetings.retry_confirmation import retry_snapshot
from src.domains.users.repository import UserRepository
from src.infrastructure.confirmed_commit import commit_confirmed_write
from src.infrastructure.meeting_retry import MeetingRetryConfirmation

if TYPE_CHECKING:
    from src.domains.meetings.service import MeetingService


async def retry_meeting(
    service: MeetingService,
    user_id: UUID,
    meeting_id: UUID,
    confirmation: MeetingRetryConfirmation | None,
) -> Meeting:
    from src.domains.meetings.service import raise_meeting_conflict, raise_meeting_not_found

    if confirmation is not None:
        actor = await UserRepository(service.db).get_by_id_for_preference_update(user_id)
        meeting = await service.repo.get_for_user(meeting_id, user_id, lock=True)
        if actor is None or meeting is None:
            raise_meeting_not_found(meeting_id)
        await confirmation.validate(await retry_snapshot(service, meeting, actor))
        await confirmation.check()
    else:
        meeting = await service._owned(meeting_id, user_id)
        if meeting.status not in (MeetingStatus.STOPPED, MeetingStatus.FAILED):
            raise_meeting_conflict("meeting_not_retryable", status=meeting.status.value)
        if meeting.audio_purged_at is not None or not (
            meeting.audio_path or await service.store.list_sequences(user_id, meeting_id)
        ):
            raise_meeting_conflict("audio_unavailable")
    if not await service.repo.requeue_for_retry(
        meeting_id, from_statuses=(MeetingStatus.STOPPED, MeetingStatus.FAILED), commit=False
    ):
        raise_meeting_conflict("meeting_not_retryable", status=meeting.status.value)
    await commit_confirmed_write(
        service.db,
        confirmation,
        {
            "meeting_retry": {
                "meeting_id": str(meeting_id),
                "status": "stopped",
                "retry_budget_reset": True,
                "processing_completed": False,
            }
        },
    )
    return await service._fresh(meeting_id, user_id)
