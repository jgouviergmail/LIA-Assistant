"""Fresh, role-correct projections of the UI's sanitized layout values."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.layout_schemas import (
    LayoutPreferenceField,
    LayoutPreferenceRead,
)
from src.domains.agents.application.schemas import ApplicationProjection
from src.infrastructure.account_preferences import layout_values


async def read_layout_preferences(
    db: AsyncSession, actor_id: UUID, request: LayoutPreferenceRead
) -> ApplicationProjection:
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    values = layout_values(actor)
    fields = request.fields if request.fields is not None else list(LayoutPreferenceField)
    return ApplicationProjection(values={field.value: values[field.value] for field in fields})
