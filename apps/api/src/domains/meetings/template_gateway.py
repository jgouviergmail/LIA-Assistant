"""The original UI service owns every native template write and callback boundary."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.meeting_templates import (
    MeetingTemplateCreate,
    MeetingTemplateResponse,
    MeetingTemplateUpdate,
    canonical_template_reference,
)
from src.domains.meetings.repository import MeetingPreferenceRepository
from src.domains.meetings.template_service import MeetingTemplateService
from src.infrastructure.meeting_templates import TemplateWriteConfirmation, TemplateWriteFacts


class SavedMeetingTemplates:
    async def creation_facts(
        self, db: AsyncSession, actor_id: UUID, request: MeetingTemplateCreate, language: str | None
    ) -> TemplateWriteFacts:
        return await MeetingTemplateService(db).creation_facts(actor_id, request, language)

    async def get(
        self, db: AsyncSession, actor_id: UUID, ref: str, language: str | None
    ) -> MeetingTemplateResponse:
        return await MeetingTemplateService(db).get(actor_id, ref, language)

    async def default_ref(self, db: AsyncSession, actor_id: UUID) -> str | None:
        preference = await MeetingPreferenceRepository(db).get_for_user(actor_id)
        return canonical_template_reference(preference.default_template_ref) if preference else None

    async def create(
        self,
        db: AsyncSession,
        actor_id: UUID,
        request: MeetingTemplateCreate,
        language: str | None,
        confirmation: TemplateWriteConfirmation,
    ) -> None:
        await MeetingTemplateService(db).create(
            actor_id, request, language, confirmation=confirmation
        )

    async def update(
        self,
        db: AsyncSession,
        actor_id: UUID,
        ref: str,
        request: MeetingTemplateUpdate,
        confirmation: TemplateWriteConfirmation,
    ) -> None:
        await MeetingTemplateService(db).update(actor_id, ref, request, confirmation=confirmation)

    async def delete(
        self, db: AsyncSession, actor_id: UUID, ref: str, confirmation: TemplateWriteConfirmation
    ) -> None:
        await MeetingTemplateService(db).delete(actor_id, ref, confirmation=confirmation)
