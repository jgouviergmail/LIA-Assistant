"""Fresh application and telephony authority precede phone identity reads and returned data."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.infrastructure.phone_identity import PhoneIdentityProjection, get_phone_identity


async def read_phone_identity(db: AsyncSession, actor_id: UUID) -> PhoneIdentityProjection:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.TELEPHONY)
    await load_actor(db, actor_id)
    result = await get_phone_identity().read(db, actor_id)
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.TELEPHONY)
    await load_actor(db, actor_id)
    return result
