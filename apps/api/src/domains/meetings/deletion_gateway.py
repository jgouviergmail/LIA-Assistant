"""The native deletion uses the original atomic owner and acknowledged cleanup."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.meetings.deletion_confirmation import deletion_snapshot
from src.domains.meetings.service import MeetingService
from src.infrastructure.meeting_deletions import (
    MeetingDeletionConfirmation,
    MeetingDeletionSnapshot,
)


class SavedMeetingDeletions:
    async def snapshot(
        self, db: AsyncSession, actor_id: UUID, meeting_id: UUID
    ) -> MeetingDeletionSnapshot:
        service = MeetingService(db)
        return await deletion_snapshot(service, await service.get(actor_id, meeting_id))

    async def delete(
        self,
        db: AsyncSession,
        actor_id: UUID,
        meeting_id: UUID,
        confirmation: MeetingDeletionConfirmation,
    ) -> None:
        await MeetingService(db).delete(actor_id, meeting_id, confirmation=confirmation)
