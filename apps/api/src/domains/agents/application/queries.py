"""Current, scoped projections using the same persisted preferences as the UI."""

from uuid import UUID

from pydantic import JsonValue, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.preference_fields import PREFERENCE_FIELDS
from src.domains.agents.application.schemas import ApplicationProjection, PreferenceRead

_JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


async def read_preferences(
    db: AsyncSession, user_id: UUID, request: PreferenceRead
) -> ApplicationProjection:
    await require_application_tools(db)
    actor = await load_actor(db, user_id)
    values: dict[str, JsonValue] = {}
    for name in request.fields if request.fields is not None else PREFERENCE_FIELDS:
        value = getattr(actor, name)
        values[name] = _JSON_VALUE.validate_python(str(value) if isinstance(value, UUID) else value)
    return ApplicationProjection(values=values)
