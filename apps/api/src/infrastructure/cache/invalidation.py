"""
Cross-worker cache invalidation via Redis Pub/Sub.

Problem:
    uvicorn --workers N uses multiprocessing. In-memory caches (class/module-level
    variables) are per-process. When an admin modifies config via API, only the
    handling worker reloads its cache — the other N-1 workers keep stale data.

Solution:
    Each cache exposes two methods:
    - ``load_*()`` — raw reload from source (DB/disk). No publish. Used at startup
      and by the subscriber.
    - ``invalidate_and_reload()`` — calls ``load_*()`` then publishes to Redis.
      Used by services/routers at runtime.

    A background subscriber task in each worker listens to the Redis channel and
    dispatches reload handlers (which call ``load_*()``, never ``invalidate_and_reload()``,
    so no infinite loop is possible).

    The publisher includes ``os.getpid()`` in the message. The subscriber skips
    messages from its own PID (the publishing worker already reloaded locally).

Usage:
    # At startup (main.py lifespan):
    register_cache("llm_config", my_reload_handler)
    task = asyncio.create_task(run_invalidation_subscriber())

    # In a cache class:
    async def invalidate_and_reload(cls, db):
        await cls.load_from_db(db)
        await publish_cache_invalidation("llm_config")

Reference: ADR-063 — docs/architecture/ADR-063-Cross-Worker-Cache-Invalidation.md
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable

from src.core.constants import REDIS_CHANNEL_CACHE_INVALIDATION
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Type alias for reload handlers: async callables with no arguments.
# Each handler is responsible for obtaining its own DB session, settings, etc.
ReloadHandler = Callable[[], Awaitable[None]]

# Module-level registry: cache_name → reload handler.
# Populated at startup via register_cache(). Read by the subscriber.
_registry: dict[str, ReloadHandler] = {}


def register_cache(cache_name: str, reload_handler: ReloadHandler) -> None:
    """Register a cache for cross-worker invalidation.

    Args:
        cache_name: Unique identifier (use ``CACHE_NAME_*`` constants).
        reload_handler: Async callable that reloads the cache from its source.
            Must be self-contained (acquire own DB session, settings, etc.).
    """
    _registry[cache_name] = reload_handler
    logger.info("cache_invalidation_handler_registered", cache_name=cache_name)


async def publish_cache_invalidation(cache_name: str) -> None:
    """Publish an invalidation event so other workers reload this cache.

    Called by ``invalidate_and_reload()`` methods after the local reload.
    Resilient: logs a warning if Redis is unavailable, never raises.

    Args:
        cache_name: Identifier of the cache that was just reloaded locally.
    """
    try:
        redis = await get_redis_cache()
        payload = json.dumps(
            {
                "cache_name": cache_name,
                "publisher_pid": os.getpid(),
            }
        )
        receivers = await redis.publish(REDIS_CHANNEL_CACHE_INVALIDATION, payload)
        logger.info(
            "cache_invalidation_published",
            cache_name=cache_name,
            publisher_pid=os.getpid(),
            receivers=receivers,
        )
    except Exception:
        logger.warning(
            "cache_invalidation_publish_failed",
            cache_name=cache_name,
            exc_info=True,
        )


def verify_registry_completeness() -> None:
    """Verify all known cache names have registered handlers.

    Called at startup to catch missing registrations early.
    Accounts for feature flags (e.g., skills may be disabled).
    """
    from src.core.config import settings
    from src.core.constants import (
        CACHE_NAME_GOOGLE_API_PRICING,
        CACHE_NAME_LLM_CONFIG,
        CACHE_NAME_PRICING,
        CACHE_NAME_SKILLS,
    )

    expected: set[str] = {CACHE_NAME_LLM_CONFIG, CACHE_NAME_PRICING, CACHE_NAME_GOOGLE_API_PRICING}
    if getattr(settings, "skills_enabled", False):
        expected.add(CACHE_NAME_SKILLS)

    registered = set(_registry.keys())
    missing = expected - registered

    if missing:
        logger.error(
            "cache_invalidation_missing_handlers",
            missing=sorted(missing),
            registered=sorted(registered),
            msg=(
                f"Cache handlers not registered: {sorted(missing)}. "
                "Cross-worker invalidation will NOT work for these caches. "
                "See ADR-063."
            ),
        )
    else:
        logger.info(
            "cache_invalidation_registry_complete",
            registered=sorted(registered),
        )


async def _handle_message(data: str) -> None:
    """Parse and dispatch a single invalidation message."""
    try:
        payload = json.loads(data)
        cache_name: str = payload["cache_name"]
        publisher_pid: int = payload["publisher_pid"]
    except (json.JSONDecodeError, KeyError):
        logger.warning("cache_invalidation_bad_message", raw=data[:200])
        return

    if publisher_pid == os.getpid():
        logger.debug("cache_invalidation_skipped_self", cache_name=cache_name)
        return

    handler = _registry.get(cache_name)
    if handler is None:
        logger.warning("cache_invalidation_unknown_cache", cache_name=cache_name)
        return

    try:
        await handler()
        logger.info(
            "cache_invalidation_reloaded",
            cache_name=cache_name,
            pid=os.getpid(),
            publisher_pid=publisher_pid,
        )
    except Exception:
        logger.error(
            "cache_invalidation_reload_failed",
            cache_name=cache_name,
            exc_info=True,
        )


async def run_invalidation_subscriber() -> None:
    """Background task: listen for invalidation events, dispatch to handlers.

    One instance per worker process, started via ``asyncio.create_task()`` in
    the lifespan startup. Auto-reconnects on Redis errors. Cleanly stops on
    ``CancelledError`` (lifespan shutdown).
    """
    reconnect_delay = 5.0
    while True:
        pubsub = None
        try:
            redis = await get_redis_cache()
            pubsub = redis.pubsub()
            await pubsub.subscribe(REDIS_CHANNEL_CACHE_INVALIDATION)
            logger.info(
                "cache_invalidation_subscriber_started",
                channel=REDIS_CHANNEL_CACHE_INVALIDATION,
                pid=os.getpid(),
            )
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=30.0,
                )
                if message is not None and message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    await _handle_message(data)
        except asyncio.CancelledError:
            logger.info("cache_invalidation_subscriber_stopped", pid=os.getpid())
            if pubsub:
                try:
                    await pubsub.unsubscribe(REDIS_CHANNEL_CACHE_INVALIDATION)
                    await pubsub.close()
                except Exception:
                    pass  # Best-effort cleanup: pubsub may already be closed
            raise
        except Exception:
            logger.error(
                "cache_invalidation_subscriber_error",
                pid=os.getpid(),
                exc_info=True,
            )
            if pubsub:
                try:
                    await pubsub.close()
                except Exception:
                    pass  # Best-effort cleanup: pubsub may already be closed
            await asyncio.sleep(reconnect_delay)
