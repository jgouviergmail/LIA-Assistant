"""Current rights protect recorded phone history before queries and returned data."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.telephony.history_schemas import PhoneHistoryProjection, PhoneHistoryRead
from src.infrastructure.phone_history import get_phone_history


async def read_phone_history(
    db: AsyncSession, actor_id: UUID, request: PhoneHistoryRead
) -> PhoneHistoryProjection:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.TELEPHONY)
    await load_actor(db, actor_id)
    result = await get_phone_history().read(db, actor_id, request)
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.TELEPHONY)
    await load_actor(db, actor_id)
    return result
