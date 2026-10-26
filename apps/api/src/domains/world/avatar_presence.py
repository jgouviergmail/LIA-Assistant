"""Best-effort public art refresh after the account transaction committed."""

from uuid import UUID

import structlog
from redis.exceptions import RedisError

from src.domains.world.avatar import AvatarPreferences
from src.domains.world.configuration import configured_store
from src.domains.world.schemas import WorldState
from src.domains.world.store import WorldUnavailable
from src.infrastructure.cache.redis import get_redis_cache

logger = structlog.get_logger(__name__)


def apply_appearance(state: WorldState, owner: str, preferences: AvatarPreferences) -> None:
    """Apply a nonstale appearance revision only to its owner's authoritative actor."""
    actor = state.actors.get(owner)
    if actor is None or preferences.revision < actor.appearance_revision:
        return
    actor.appearance = preferences.appearance
    actor.appearance_revision = preferences.revision


async def refresh_avatar_presence(owner: UUID, preferences: AvatarPreferences) -> None:
    """Publish the owner's saved appearance through the shared Redis transaction."""
    try:
        store = configured_store(await get_redis_cache())
        state, _ = await store.read()
        if str(owner) not in state.actors:
            return
        await store.update(lambda current, _now: apply_appearance(current, str(owner), preferences))
    except (RedisError, WorldUnavailable, TimeoutError, ValueError) as exc:
        # Persistence succeeded. The existing fresh policy loop repairs this view.
        logger.warning("world_avatar_presence_deferred", reason=type(exc).__name__)
