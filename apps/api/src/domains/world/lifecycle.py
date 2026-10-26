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
from src.domains.world.configuration import configured_authority
from src.domains.world.mailbox import WorldMailbox
from src.domains.world.public_mailbox import PublicMailbox
from src.domains.world.schemas import WorldState
from src.domains.world.store import WorldStore, WorldUnavailable
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
            except WorldUnavailable, ValidationError:
                logger.warning("world_cleanup_corrupt_authority")
                continue
            if (
                account in state.actors
                or account in state.presences
                or any(w.account_id == account for w in state.queue)
            ):
                await store.update(remove)
        await _purge_messages(redis, account)


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
