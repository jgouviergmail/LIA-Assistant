"""Exact opt-in discovery shares UI anti-enumeration budget and neutral source guards."""

from datetime import UTC, datetime
from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.peer_discovery_schemas import (
    PeerDiscoveryProjection,
    PeerDiscoveryQuery,
)
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.peers.service import PeersService
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter


async def search_peer_directory(
    db: AsyncSession, actor_id: UUID, query: PeerDiscoveryQuery
) -> PeerDiscoveryProjection:
    selected = PeerDiscoveryQuery.model_validate(query.model_dump())

    async def check() -> None:
        await require_application_tools(db)
        await require_capability_fresh(db, PlatformCapability.PEERS)
        await load_actor(db, actor_id)

    await check()
    try:
        limiter = await get_rate_limiter()
        allowed = await limiter.acquire(
            key=f"auth:peers_discovery:user:{actor_id}",
            max_calls=settings.peers_discovery_rate_limit_calls,
            window_seconds=settings.peers_discovery_rate_limit_window_seconds,
        )
    except RedisError as exc:
        raise CommandRejected("DEPENDENCY_ERROR") from exc
    if not allowed:
        raise CommandRejected("RATE_LIMIT_EXCEEDED")
    await check()
    matches = await PeersService(db).search_discoverable(actor_id, selected.query)
    await check()
    matches.sort(key=lambda item: item.peer_id)
    next_offset = selected.offset + selected.limit
    result = PeerDiscoveryProjection(
        matches=matches[selected.offset : next_offset],
        total=len(matches),
        next_offset=next_offset if next_offset < len(matches) else None,
        observed_at=datetime.now(UTC),
    )
    if len(result.model_dump_json().encode("utf-8")) > 64_000:
        raise ValueError("Directory page exceeds native bound; request a smaller page")
    return result
