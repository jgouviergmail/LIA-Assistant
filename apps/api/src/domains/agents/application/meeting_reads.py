"""Fresh, fail-closed meeting reads do not initiate a recording or model job."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.meeting_preferences import require_meeting_preferences
from src.domains.agents.application.meeting_read_budget import (
    bound_meeting_page,
    meeting_read_token_budget,
)
from src.infrastructure.meeting_reads import (
    MEETING_READ_MAX_BYTES,
    MeetingReadInput,
    MeetingReadPage,
    TemplateReadInput,
    get_meeting_reads,
)


async def read_meeting_view(
    db: AsyncSession, actor_id: UUID, query: MeetingReadInput | TemplateReadInput
) -> MeetingReadPage:
    actor = await require_meeting_preferences(db, actor_id)
    gateway = get_meeting_reads()
    if isinstance(query, MeetingReadInput):
        selected = MeetingReadInput.model_validate(query.model_dump())
        page = await gateway.meetings(db, actor_id, selected)
    else:
        template = TemplateReadInput.model_validate(query.model_dump())
        page = await gateway.templates(db, actor_id, template, actor.language)
    await require_meeting_preferences(db, actor_id)
    page = bound_meeting_page(page, meeting_read_token_budget())
    if len(page.model_dump_json().encode("utf-8")) > MEETING_READ_MAX_BYTES:
        raise ValueError("Meeting observation too large; request a smaller page")
    return page
