"""Private passive scenery: native cached weather and a server civil-clock anchor."""

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import Field

from src.core.config import settings
from src.core.exceptions import CacheError
from src.core.private_input_route import PrivateApplicationInputRoute
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.briefing.companion import CompanionEnvironment, project_weather
from src.domains.briefing.service import BriefingService
from src.domains.feature_switches.guard import (
    capability_dependencies,
    require_capability_fresh,
)
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context


class WorldEnvironment(CompanionEnvironment):
    server_time: float = Field(
        ge=0,
        description="Authoritative Unix-seconds clock anchor for client freshness and expiry display.",
    )


async def read_environment(user: User) -> WorldEnvironment:
    """Borrow cached weather and the owner's timezone with a server clock anchor; call no provider."""
    async with asyncio.timeout(settings.world_policy_timeout):
        async with get_db_context() as db:
            await require_capability_fresh(db, PlatformCapability.WORLD)
        service = BriefingService(user)
        weather = await service.read_cached_weather()
        now = datetime.now(UTC)
        return WorldEnvironment(
            timezone=str(service.user_tz),
            weather=project_weather(weather, now),
            server_time=now.timestamp(),
        )


router = APIRouter(
    route_class=PrivateApplicationInputRoute,
    dependencies=capability_dependencies(PlatformCapability.WORLD),
)


@router.get("/environment", response_model=WorldEnvironment)
async def environment(
    user: User = Depends(get_current_active_session_for_stream),
) -> WorldEnvironment:
    """Return authenticated private scenery, translating policy timeouts to cache errors."""
    try:
        return await read_environment(user)
    except TimeoutError:
        raise CacheError("world_environment") from None
