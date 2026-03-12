"""
Distributed lock for scheduled jobs using Redis SETNX pattern.

Prevents duplicate job execution when running multiple uvicorn workers.
Each worker's APScheduler triggers the same jobs, but only one should execute.

Pattern:
- Try to acquire lock with SETNX (atomic Set if Not eXists)
- If acquired: execute job, release lock on completion
- If not acquired: skip silently (another worker is executing)
- Auto-expire lock (TTL) as safety net for crashed workers

Reference:
- ShedLock (Java): https://github.com/lukas-krecan/ShedLock
- Similar pattern used by Celery Beat with Redis
"""

from typing import Any

import redis.asyncio as aioredis
import structlog

from src.core.constants import SCHEDULER_LOCK_DEFAULT_TTL_SECONDS

logger = structlog.get_logger(__name__)


class SchedulerLock:
    """
    Distributed lock for scheduled jobs using Redis SETNX.

    Unlike OAuthLock which retries, SchedulerLock skips immediately if busy.
    This is the correct behavior for scheduler jobs: only one worker should
    execute, others should silently skip.

    Example:
        >>> redis_client = await get_redis_cache()
        >>> async with SchedulerLock(redis_client, "interest_notification") as lock:
        ...     if lock.acquired:
        ...         await process_interest_notifications()
        ...     # else: another worker is executing, skip silently
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        job_id: str,
        ttl_seconds: int = SCHEDULER_LOCK_DEFAULT_TTL_SECONDS,
    ) -> None:
        """
        Initialize scheduler lock.

        Args:
            redis_client: Redis async client.
            job_id: Unique job identifier (e.g., "interest_notification").
            ttl_seconds: Lock TTL in seconds (safety net for crashes).
        """
        self.redis = redis_client
        self.job_id = job_id
        self.ttl_seconds = ttl_seconds

        # Lock key: scheduler_lock:{job_id}
        self.lock_key = f"scheduler_lock:{job_id}"
        self.acquired = False

    async def __aenter__(self) -> "SchedulerLock":
        """
        Try to acquire lock (non-blocking).

        Returns:
            Self with .acquired indicating if lock was obtained.
        """
        # Try to acquire lock using SETNX (SET if Not eXists)
        result = await self.redis.set(
            self.lock_key,
            "locked",
            nx=True,  # Only set if key doesn't exist
            ex=self.ttl_seconds,  # Auto-expire as safety net
        )

        self.acquired = bool(result)

        if self.acquired:
            logger.debug(
                "scheduler_lock_acquired",
                job_id=self.job_id,
                ttl_seconds=self.ttl_seconds,
            )
        else:
            logger.debug(
                "scheduler_lock_busy_skipping",
                job_id=self.job_id,
            )

        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """
        Exit context manager WITHOUT releasing the lock.

        The lock is intentionally NOT deleted here. It expires naturally via its
        TTL (default 5 minutes). This prevents other workers from acquiring the
        lock and re-executing the same job within the same scheduler interval.

        Previous bug: the lock was deleted on exit (~0.02s after acquisition),
        allowing all N workers to execute sequentially within the same interval.

        Args:
            exc_type: Exception type if error occurred.
            exc_val: Exception value.
            exc_tb: Exception traceback.
        """
        if self.acquired:
            logger.debug(
                "scheduler_lock_exit_ttl_retained",
                job_id=self.job_id,
                ttl_seconds=self.ttl_seconds,
            )
