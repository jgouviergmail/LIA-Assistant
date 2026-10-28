"""One settings projection for every authority transition, including lifecycle cleanup."""

from redis.asyncio import Redis

from src.core.config import settings
from src.domains.world.authority import Authority, Limits
from src.domains.world.game_context import GameLimits
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


def configured_arcade_enabled() -> bool:
    """Expose only the subordinate deployment ceiling; native fresh World policy still gates commands."""
    return settings.world_enabled and settings.world_arcade_enabled


def configured_game_limits() -> GameLimits:
    """Use one effective settings projection for commands, views and account erasure."""
    return GameLimits(
        wait_seconds=settings.world_arcade_wait_seconds,
        request_seconds=settings.world_arcade_request_seconds,
        reconnect_seconds=settings.world_arcade_reconnect_seconds,
        turn_seconds=settings.world_arcade_turn_seconds,
        round_seconds=settings.world_arcade_round_seconds,
        result_seconds=settings.world_arcade_result_seconds,
    )


def configured_store(redis: Redis) -> WorldStore:
    """Build a scene-scoped Redis store with the effective namespace, TTL and timeout."""
    return WorldStore(
        redis,
        namespace=settings.world_namespace,
        ttl=settings.world_state_seconds,
        timeout=settings.world_authority_timeout,
    )
