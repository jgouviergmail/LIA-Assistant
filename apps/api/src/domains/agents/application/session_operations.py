"""Fresh authority protects session metadata before Redis access and before projection."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.session_schemas import DeviceSessionsRead
from src.domains.auth.session_queries import DeviceSessionsProjection, read_device_sessions
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore


async def read_session_settings(
    db: AsyncSession,
    actor_id: UUID,
    request: DeviceSessionsRead,
    *,
    origin: ApplicationOrigin | None = None,
) -> DeviceSessionsProjection:
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    store = SessionStore(await get_redis_session())
    result = await read_device_sessions(
        db, actor, store, cursor=request.cursor, limit=request.limit
    )
    if origin is not None:
        facts = await origin.require_session(actor_id, expected_binding=origin.binding_id)
        result = result.model_copy(
            update={
                "current_session_known": True,
                "sessions": [
                    item.model_copy(update={"current": item.id == facts.display_id})
                    for item in result.sessions
                ],
            }
        )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return result
