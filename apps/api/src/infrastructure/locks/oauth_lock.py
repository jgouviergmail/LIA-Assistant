"""
OAuth refresh token lock using Redis SETNX pattern.

Prevents race conditions when multiple requests try to refresh expired tokens simultaneously.
This is an infrastructure concern used by connector clients for OAuth token management.
"""

import asyncio
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
import structlog

from src.core.constants import (
    OAUTH_LOCK_MAX_BACKOFF_EXPONENT,
    OAUTH_LOCK_RETRY_INTERVAL_MS,
    OAUTH_LOCK_TIMEOUT_SECONDS,
)
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)


class OAuthLock:
    """
    Distributed lock for OAuth token refresh operations using Redis SETNX.

    Ensures only one refresh operation occurs at a time per user/connector combination.
    Uses async context manager pattern for automatic lock acquisition and release.

    Example:
        >>> redis_client = await get_redis_session()
        >>> async with OAuthLock(redis_client, user_id, ConnectorType.GOOGLE_CONTACTS):
        ...     # Refresh token safely - only one coroutine executes this block
        ...     await refresh_oauth_token(...)
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        user_id: UUID,
        connector_type: ConnectorType,
        timeout_seconds: int = OAUTH_LOCK_TIMEOUT_SECONDS,
        retry_interval_ms: int = OAUTH_LOCK_RETRY_INTERVAL_MS,
    ) -> None:
        """
        Initialize OAuth lock.

        Args:
            redis_client: Redis async client.
            user_id: User UUID.
            connector_type: Type of connector.
            timeout_seconds: Lock TTL in seconds (default 10s).
            retry_interval_ms: Retry interval if lock busy (default 100ms).
        """
        self.redis = redis_client
        self.user_id = user_id
        self.connector_type = connector_type
        self.timeout_seconds = timeout_seconds
        self.retry_interval_ms = retry_interval_ms

        # Lock key: oauth_lock:{user_id}:{connector_type}
        self.lock_key = f"oauth_lock:{user_id}:{connector_type.value}"
        self.lock_acquired = False

    async def __aenter__(self) -> "OAuthLock":
        """
        Acquire lock with exponential backoff retry.
        Blocks until lock is acquired or raises TimeoutError.

        Returns:
            Self for context manager pattern.

        Raises:
            TimeoutError: If lock cannot be acquired within timeout period.
        """
        start_time = asyncio.get_event_loop().time()
        max_wait_time = self.timeout_seconds
        connector_type_value = self.connector_type.value

        retry_count = 0
        while True:
            # Try to acquire lock using SETNX (SET if Not eXists)
            acquired = await self.redis.set(
                self.lock_key,
                "locked",
                nx=True,  # Only set if key doesn't exist
                ex=self.timeout_seconds,  # Auto-expire after timeout
            )

            if acquired:
                self.lock_acquired = True
                # Prometheus: track acquisition latency + contention if we waited.
                # Wrapped defensively — lock acquisition must never fail due to metrics.
                try:
                    from src.infrastructure.observability.metrics import (
                        oauth_lock_acquired_total,
                        oauth_lock_contention_total,
                        oauth_lock_wait_duration_seconds,
                    )

                    oauth_lock_acquired_total.labels(connector_type=connector_type_value).inc()
                    oauth_lock_wait_duration_seconds.labels(
                        connector_type=connector_type_value
                    ).observe(asyncio.get_event_loop().time() - start_time)
                    if retry_count > 0:
                        oauth_lock_contention_total.labels(
                            connector_type=connector_type_value
                        ).inc()
                except Exception:
                    pass
                logger.debug(
                    "oauth_lock_acquired",
                    user_id=str(self.user_id),
                    connector_type=connector_type_value,
                    retry_count=retry_count,
                )
                return self

            # Lock is busy - check if we should retry
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= max_wait_time:
                try:
                    from src.infrastructure.observability.metrics import (
                        oauth_lock_timeout_total,
                        oauth_lock_wait_duration_seconds,
                    )

                    oauth_lock_timeout_total.labels(connector_type=connector_type_value).inc()
                    oauth_lock_wait_duration_seconds.labels(
                        connector_type=connector_type_value
                    ).observe(elapsed)
                except Exception:
                    pass
                logger.error(
                    "oauth_lock_timeout",
                    user_id=str(self.user_id),
                    connector_type=connector_type_value,
                    elapsed_seconds=elapsed,
                    retry_count=retry_count,
                )
                raise TimeoutError(
                    f"Could not acquire OAuth lock for {connector_type_value} "
                    f"after {elapsed:.2f}s"
                )

            # Exponential backoff with jitter
            retry_count += 1
            wait_time = min(
                self.retry_interval_ms
                * (2 ** min(retry_count - 1, OAUTH_LOCK_MAX_BACKOFF_EXPONENT))
                / 1000,
                1.0,  # Cap at 1 second
            )

            logger.debug(
                "oauth_lock_busy_retrying",
                user_id=str(self.user_id),
                connector_type=connector_type_value,
                retry_count=retry_count,
                wait_time_ms=int(wait_time * 1000),
            )

            await asyncio.sleep(wait_time)

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """
        Release lock when exiting context manager.

        Args:
            exc_type: Exception type if error occurred.
            exc_val: Exception value.
            exc_tb: Exception traceback.
        """
        if self.lock_acquired:
            try:
                await self.redis.delete(self.lock_key)
                try:
                    from src.infrastructure.observability.metrics import (
                        oauth_lock_released_total,
                    )

                    oauth_lock_released_total.labels(connector_type=self.connector_type.value).inc()
                except Exception:
                    pass
                logger.debug(
                    "oauth_lock_released",
                    user_id=str(self.user_id),
                    connector_type=self.connector_type.value,
                )
            except Exception as e:
                logger.warning(
                    "oauth_lock_release_failed",
                    user_id=str(self.user_id),
                    connector_type=self.connector_type.value,
                    error=str(e),
                )
                # Don't raise - lock will auto-expire

    async def is_locked(self) -> bool:
        """
        Check if lock is currently held (by any process).

        Returns:
            True if lock exists in Redis, False otherwise.
        """
        exists = await self.redis.exists(self.lock_key)
        return bool(exists)

    async def force_release(self) -> None:
        """
        Force release lock (use with caution).
        Should only be used in cleanup/admin scenarios.
        """
        deleted = await self.redis.delete(self.lock_key)
        if deleted:
            logger.warning(
                "oauth_lock_force_released",
                user_id=str(self.user_id),
                connector_type=self.connector_type.value,
            )
