"""Read saved account location only; device location has a separate authenticated bridge."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.location_schemas import LocationField, LocationRead
from src.domains.agents.application.schemas import ApplicationProjection
from src.domains.users.home_location_commands import location_values


async def read_locations(
    db: AsyncSession, actor_id: UUID, request: LocationRead
) -> ApplicationProjection:
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    fields = request.fields if request.fields is not None else list(LocationField)
    return ApplicationProjection(values=location_values(actor, {field.value for field in fields}))
