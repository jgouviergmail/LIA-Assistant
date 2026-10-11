"""Resolve and seal the exact selected template against the original owned source."""

from typing import TYPE_CHECKING
from uuid import UUID

from src.core.config import settings
from src.core.meeting_reformat import MeetingReformatRequest
from src.domains.meetings.models import Meeting
from src.domains.meetings.regeneration_confirmation import regeneration_snapshot
from src.domains.meetings.template_service import MeetingTemplateService
from src.domains.users.models import User
from src.domains.users.repository import UserRepository
from src.infrastructure.meeting_reformat import MeetingReformatConfirmation, MeetingReformatSnapshot
from src.infrastructure.meeting_regeneration import RegenerationTemplate

if TYPE_CHECKING:
    from src.domains.meetings.service import MeetingService


async def reformat_snapshot(
    service: MeetingService,
    meeting: Meeting,
    actor: User,
    request: MeetingReformatRequest,
    *,
    destination_id: UUID,
) -> MeetingReformatSnapshot:
    resolved = await MeetingTemplateService(service.db).resolve(
        actor.id, request.template_ref, actor.language
    )
    definition = RegenerationTemplate.model_validate(
        {
            "ref": str(resolved.ref),
            "name": resolved.name,
            "sections": [section.model_dump(mode="json") for section in resolved.sections],
        }
    )
    source = await regeneration_snapshot(
        service, meeting, actor, template=definition, allow_regeneration=request.mode == "new"
    )
    return MeetingReformatSnapshot.model_validate(
        {
            "source": source,
            "request": request.model_dump(mode="json"),
            "destination_id": destination_id,
            "rag_enabled_at_confirmation": settings.rag_spaces_enabled,
        }
    )


async def confirmed_reformat_source(
    service: MeetingService,
    actor_id: UUID,
    meeting_id: UUID,
    request: MeetingReformatRequest,
    confirmation: MeetingReformatConfirmation,
) -> Meeting:
    from src.domains.meetings.service import raise_meeting_not_found

    actor = await UserRepository(service.db).get_by_id_for_preference_update(actor_id)
    meeting = await service.repo.get_for_user(meeting_id, actor_id, lock=True)
    if actor is None or meeting is None:
        raise_meeting_not_found(meeting_id)
    actual = await reformat_snapshot(
        service, meeting, actor, request, destination_id=confirmation.destination_id
    )
    await confirmation.validate(actual)
    await confirmation.check()
    return meeting
