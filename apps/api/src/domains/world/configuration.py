"""One settings projection for every authority transition, including lifecycle cleanup."""

from redis.asyncio import Redis

from src.core.config import settings
from src.domains.world.authority import Authority, Limits
from src.domains.world.store import WorldStore


def configured_authority() -> Authority:
    """Build the pure authority from the effective World settings."""
    return Authority(
        Limits(
            capacity=settings.world_capacity,
            queue_size=settings.world_queue_size,
            lease_seconds=settings.world_lease_seconds,
            queue_seconds=settings.world_queue_seconds,
            offer_seconds=settings.world_offer_seconds,
            idle_seconds=settings.world_idle_seconds,
        )
    )


def configured_store(redis: Redis) -> WorldStore:
    """Build a scene-scoped Redis store with the effective namespace, TTL and timeout."""
    return WorldStore(
        redis,
        namespace=settings.world_namespace,
        ttl=settings.world_state_seconds,
        timeout=settings.world_authority_timeout,
    )
