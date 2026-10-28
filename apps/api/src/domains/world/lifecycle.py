"""Selective removal from mixed-account authority, never deletion of a shared world."""

import asyncio
import re
from uuid import UUID

import structlog
from pydantic import ValidationError
from redis.asyncio import Redis

from src.core.config import settings
from src.core.constants import (
    REDIS_KEY_WORLD_MESSAGE_PREFIX,
    REDIS_KEY_WORLD_RUNTIME_PREFIX,
)
from src.domains.world.collision import SCENE
from src.domains.world.configuration import configured_authority, configured_game_limits
from src.domains.world.game_erasure import has_game_account, purge_game_account
from src.domains.world.legacy_state import LegacyWorldStore, LegacyWorldStoreV2
from src.domains.world.mailbox import WorldMailbox
from src.domains.world.public_mailbox import PublicMailbox
from src.domains.world.schemas import WorldState, WorldStateShape
from src.domains.world.store import AuthorityStore, WorldStore, WorldUnavailable
from src.infrastructure.cache.redis import get_redis_cache

logger = structlog.get_logger(__name__)


def _authority_target(key: str) -> tuple[str, str] | None:
    """Recognize an owned authority key and its scene for account cleanup."""
    namespace, separator, scene = key.removeprefix(REDIS_KEY_WORLD_RUNTIME_PREFIX).partition(":")
    # Only authority versions, never socket leases, counters or foreign key families.
    scene_name = re.escape(SCENE.rsplit(":", 1)[0])
    if not namespace or (separator and not re.fullmatch(rf"{scene_name}:[1-9][0-9]*", scene)):
        return None
    return namespace, scene


async def purge_world_account(redis: Redis, account: str) -> None:
    """CAS-remove the owner while retaining peers, epoch and FIFO reservations.

    Admission takes the native user row lock, so a stale controller cannot
    recreate the account after deactivation or the deletion transaction.
    Socket/IP counters share the prefix but are not authority documents.
    """
    account = str(UUID(account))
    authority = configured_authority()

    def remove(state: WorldState, now: float) -> None:
        """Remove this account's actor and waiter from one watched authority snapshot."""
        state.actors.pop(account, None)
        state.presences.pop(account, None)
        state.queue = [waiter for waiter in state.queue if waiter.account_id != account]
        purge_game_account(state, account, now, configured_game_limits())
        authority.prune(state, now)

    async with asyncio.timeout(settings.world_policy_timeout + settings.world_authority_timeout):
        async for raw in redis.scan_iter(match=f"{REDIS_KEY_WORLD_RUNTIME_PREFIX}*", count=100):
            key = raw.decode() if isinstance(raw, bytes) else raw
            target = _authority_target(key)
            if target is None:
                continue
            namespace, scene = target
            store = WorldStore(
                redis,
                namespace=namespace,
                ttl=settings.world_state_seconds,
                scene=scene or None,
            )
            try:
                state, _ = await store.read()
            except ValidationError:
                await _purge_legacy(redis, namespace, scene, account)
                continue
            except WorldUnavailable as unavailable:
                # Read-side, only the byte ceiling raises it: the record is oversized.
                logger.warning("world_cleanup_authority_unreadable", error_code=unavailable.code)
                continue
            if _has_account(state, account):
                await store.update(remove)
        await _purge_messages(redis, account)
        await _purge_game_rate(redis, account)


async def _purge_game_rate(redis: Redis, account: str) -> None:
    """Erase the owner's short-lived distributed command counters without touching peers."""
    async for raw in redis.scan_iter(
        match=f"{REDIS_KEY_WORLD_RUNTIME_PREFIX}*:game-rate:{account}", count=100
    ):
        key = raw.decode() if isinstance(raw, bytes) else raw
        await redis.delete(key)


def _has_account(state: WorldStateShape, account: str) -> bool:
    """Share the complete bounded actor/presence/queue erasure predicate across generations."""
    if isinstance(state, WorldState) and has_game_account(state, account):
        return True
    return (
        account in state.actors
        or account in state.presences
        or any(waiter.account_id == account for waiter in state.queue)
    )


async def _purge_legacy(redis: Redis, namespace: str, scene: str, account: str) -> None:
    """Try only declared older generations, preserving each original nested field set.

    Each outcome is logged as what it is: an oversized record or a contended commit
    is unavailable, and only a record no declared generation reads is corrupt.
    """
    try:
        if await _erase_legacy(
            LegacyWorldStore(
                redis, namespace=namespace, ttl=settings.world_state_seconds, scene=scene or None
            ),
            account,
        ):
            return
        if await _erase_legacy(
            LegacyWorldStoreV2(
                redis, namespace=namespace, ttl=settings.world_state_seconds, scene=scene or None
            ),
            account,
        ):
            return
    except WorldUnavailable as unavailable:
        logger.warning("world_cleanup_authority_unavailable", error_code=unavailable.code)
        return
    logger.warning("world_cleanup_corrupt_authority")


async def _erase_legacy[State: WorldStateShape](store: AuthorityStore[State], account: str) -> bool:
    """Perform generation-typed erasure without invoking current actor/game pruning."""

    def remove(state: State, _now: float) -> None:
        """Remove only the requested account without applying newer scene transitions."""
        state.actors.pop(account, None)
        state.presences.pop(account, None)
        state.queue = [waiter for waiter in state.queue if waiter.account_id != account]

    try:
        state, _ = await store.read()
        if _has_account(state, account):
            await store.update(remove)
        return True
    except ValidationError:
        return False


async def _purge_messages(redis: Redis, account: str) -> None:
    # An index may have been evicted, trimmed or corrupted while its bodies
    # still live. It is not a complete inventory for erasure.
    """Scan bounded message batches and remove only this account's bodies and indexes."""
    for family in ("inbox", "public-inbox"):
        async for raw in redis.scan_iter(
            match=f"{REDIS_KEY_WORLD_MESSAGE_PREFIX}*:{family}:{account}", count=100
        ):
            key = raw.decode() if isinstance(raw, bytes) else raw
            parts = key.split(":")
            if len(parts) == 5 and parts[3] == family:
                await redis.delete(key)
    for family in ("body", "public-body"):
        batch: list[str] = []
        async for raw in redis.scan_iter(
            match=f"{REDIS_KEY_WORLD_MESSAGE_PREFIX}*:{family}:*", count=100
        ):
            key = raw.decode() if isinstance(raw, bytes) else raw
            parts = key.split(":")
            if len(parts) != 5 or parts[3] != family:
                continue
            batch.append(key)
            if len(batch) >= 100:
                await _purge_body_batch(redis, account, batch)
                batch.clear()
        if batch:
            await _purge_body_batch(redis, account, batch)


async def _purge_body_batch(redis: Redis, account: str, keys: list[str]) -> None:
    """Decode one bounded batch and delete only messages involving the erased account."""
    owned: list[str] = []
    for key, body in zip(keys, await redis.mget(keys), strict=True):
        if body is None:
            continue
        try:
            if key.split(":")[-2] == "public-body":
                public_message = PublicMailbox.decode(body)
                erased = (
                    account == public_message.sender.account or account in public_message.recipients
                )
            else:
                message = WorldMailbox.decode(body)
                erased = account in {message.sender.account, message.recipient.account}
        except WorldUnavailable:
            # Do not guess ownership or let an unrelated corrupt item prevent
            # erasure of valid bodies. Unreadable content retains its expiry.
            logger.warning("world_cleanup_corrupt_message")
            continue
        if erased:
            owned.append(key)
    if owned:
        await redis.delete(*owned)


async def purge_world_account_best_effort(user_id: UUID) -> None:
    """Account deletion must continue its other purges if the cache is unavailable."""
    try:
        async with asyncio.timeout(
            settings.world_policy_timeout + settings.world_authority_timeout
        ):
            await purge_world_account(await get_redis_cache(), str(user_id))
    except Exception as exc:
        logger.warning("world_account_purge_failed", error_type=type(exc).__name__)
