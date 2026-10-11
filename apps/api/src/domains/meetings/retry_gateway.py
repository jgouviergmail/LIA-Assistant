"""Requeue with the original durable worker and known-commit follow-up only."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.meetings.retry_confirmation import retry_snapshot
from src.domains.meetings.service import MeetingService, raise_meeting_not_found
from src.domains.users.repository import UserRepository
from src.infrastructure.meeting_retry import MeetingRetryConfirmation, MeetingRetrySnapshot


class SavedMeetingRetry:
    async def snapshot(
        self, db: AsyncSession, actor_id: UUID, meeting_id: UUID
    ) -> MeetingRetrySnapshot:
        actor = await UserRepository(db).get_by_id(actor_id)
        if actor is None:
            raise_meeting_not_found(meeting_id)
        service = MeetingService(db)
        return await retry_snapshot(service, await service.get(actor_id, meeting_id), actor)

    async def retry(
        self,
        db: AsyncSession,
        actor_id: UUID,
        meeting_id: UUID,
        confirmation: MeetingRetryConfirmation,
    ) -> None:
        try:
            await MeetingService(db).retry(actor_id, meeting_id, confirmation=confirmation)
        finally:
            if confirmation.receipt.committed:
                from src.domains.meetings.processing import launch_processing

                launch_processing(meeting_id)
