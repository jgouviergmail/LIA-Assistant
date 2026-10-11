"""Only an acknowledged original rewrite queue starts the fenced background job."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.meeting_reformat import MeetingReformatRequest
from src.domains.meetings.reformat import reformat_meeting
from src.domains.meetings.reformat_confirmation import reformat_snapshot
from src.domains.meetings.service import MeetingService, raise_meeting_not_found
from src.domains.users.repository import UserRepository
from src.infrastructure.meeting_reformat import MeetingReformatConfirmation, MeetingReformatSnapshot


class SavedMeetingReformat:
    async def snapshot(
        self,
        db: AsyncSession,
        actor_id: UUID,
        meeting_id: UUID,
        request: MeetingReformatRequest,
        *,
        destination_id: UUID,
    ) -> MeetingReformatSnapshot:
        actor = await UserRepository(db).get_by_id(actor_id)
        if actor is None:
            raise_meeting_not_found(meeting_id)
        service = MeetingService(db)
        return await reformat_snapshot(
            service,
            await service.get(actor_id, meeting_id),
            actor,
            request,
            destination_id=destination_id,
        )

    async def reformat(
        self,
        db: AsyncSession,
        actor_id: UUID,
        selected: MeetingReformatSnapshot,
        confirmation: MeetingReformatConfirmation,
    ) -> None:
        try:
            await reformat_meeting(
                MeetingService(db),
                actor_id,
                selected.source.meeting_id,
                selected.request,
                selected.source.language,
                confirmation=confirmation,
            )
        finally:
            if confirmation.receipt.committed:
                from src.domains.meetings.regeneration import launch_regenerate

                launch_regenerate(selected.destination_id)
