"""A known queue commit alone invokes the original fenced rebuild worker."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.meetings.regeneration_confirmation import regeneration_snapshot
from src.domains.meetings.service import MeetingService, raise_meeting_not_found
from src.domains.users.repository import UserRepository
from src.infrastructure.meeting_regeneration import (
    MeetingRegenerationConfirmation,
    MeetingRegenerationSnapshot,
)


class SavedMeetingRegeneration:
    async def snapshot(
        self, db: AsyncSession, actor_id: UUID, meeting_id: UUID
    ) -> MeetingRegenerationSnapshot:
        actor = await UserRepository(db).get_by_id(actor_id)
        if actor is None:
            raise_meeting_not_found(meeting_id)
        service = MeetingService(db)
        return await regeneration_snapshot(service, await service.get(actor_id, meeting_id), actor)

    async def regenerate(
        self,
        db: AsyncSession,
        actor_id: UUID,
        meeting_id: UUID,
        confirmation: MeetingRegenerationConfirmation,
    ) -> None:
        try:
            await MeetingService(db).regenerate(actor_id, meeting_id, confirmation=confirmation)
        finally:
            if confirmation.receipt.committed:
                from src.domains.meetings.regeneration import launch_regenerate

                launch_regenerate(meeting_id)
