"""Current saved assistant settings; no stored secret or inferred default."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.assistant_schemas import (
    AssistantPreferenceField,
    AssistantPreferenceRead,
)
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.schemas import ApplicationProjection
from src.domains.auth.preference_commands import AssistantPreferencePatch


async def read_assistant_preferences(
    db: AsyncSession, actor_id: UUID, request: AssistantPreferenceRead
) -> ApplicationProjection:
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    fields = request.fields if request.fields is not None else list(AssistantPreferenceField)
    values = AssistantPreferencePatch.model_validate(
        {field.value: getattr(actor, field.value) for field in fields}
    )
    return ApplicationProjection(values=values.model_dump(mode="json", exclude_unset=True))
