"""
Distributed leader election for APScheduler using Redis SETNX.

Ensures exactly one APScheduler instance runs across multiple uvicorn workers.
Handles stale locks from killed workers via non-blocking background re-election.

Design:
- Single SETNX attempt at startup (non-blocking)
- If lock is stale, background asyncio.Task retries every N seconds
- When lock is acquired, scheduler.start() is called (even mid-flight)
- Lock is renewed via a scheduler job (every 30s, TTL 120s)
- On shutdown, lock is released for fast takeover

This class is the single source of truth for leader election logic.
Workers (main.py) only need to create an instance, register jobs, call start/shutdown.
"""

import asyncio
import os
import time
from collections.abc import Awaitable, Callable

import redis.asyncio as aioredis
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.core.constants import (
    SCHEDULER_JOB_LEADER_LOCK_RENEWAL,
    SCHEDULER_LEADER_LOCK_KEY,
    SCHEDULER_LEADER_LOCK_TTL_SECONDS,
    SCHEDULER_LEADER_RE_ELECTION_INTERVAL_SECONDS,
    SCHEDULER_LEADER_RENEW_INTERVAL_SECONDS,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class SchedulerLeaderElector:
    """
    Distributed leader election for APScheduler using Redis SETNX.

    Ensures exactly one APScheduler instance runs across multiple uvicorn
    workers. Handles stale locks from killed workers via non-blocking
    background re-election.

    Usage:
        elector = SchedulerLeaderElector(redis, scheduler, on_elected=callback)
        # ... register jobs with scheduler.add_job() ...
        await elector.start()     # Try acquire, start background re-election if needed
        # ... app runs ...
        await elector.shutdown()  # Release lock, stop scheduler

    Args:
        redis: Redis async client (None triggers single-worker fallback).
        scheduler: APScheduler AsyncIOScheduler instance.
        lock_key: Redis key for the leader lock.
        lock_ttl_seconds: Lock TTL in seconds (safety net for crashes).
        renew_interval_seconds: How often to renew the lock TTL.
        re_election_interval_seconds: How often to retry acquiring in background.
        on_elected: Optional async callback invoked once when leadership is acquired.
    """

    def __init__(
        self,
        redis: aioredis.Redis | None,
        scheduler: AsyncIOScheduler,
        *,
        lock_key: str = SCHEDULER_LEADER_LOCK_KEY,
        lock_ttl_seconds: int = SCHEDULER_LEADER_LOCK_TTL_SECONDS,
        renew_interval_seconds: int = SCHEDULER_LEADER_RENEW_INTERVAL_SECONDS,
        re_election_interval_seconds: int = SCHEDULER_LEADER_RE_ELECTION_INTERVAL_SECONDS,
        on_elected: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._redis = redis
        self._scheduler = scheduler
        self._lock_key = lock_key
        self._lock_ttl = lock_ttl_seconds
        self._renew_interval = renew_interval_seconds
        self._re_election_interval = re_election_interval_seconds
        self._on_elected = on_elected

        self._worker_id: str = f"worker-{os.getpid()}"
        self._is_leader: bool = False
        self._elected_at: float | None = None  # monotonic timestamp
        self._re_election_task: asyncio.Task[None] | None = None

    @property
    def is_leader(self) -> bool:
        """Whether this worker currently holds scheduler leadership."""
        return self._is_leader

    async def start(self) -> None:
        """
        Attempt to acquire scheduler leadership (non-blocking).

        1. If no Redis: become leader immediately (single-worker fallback).
        2. Try SETNX once.
        3. If acquired: start scheduler via _become_leader().
        4. If not: log stale lock details, spawn background re-election task.
        """
        # Guard against double-start (would orphan the re-election task)
        if self._is_leader or self._re_election_task is not None:
            return

        logger.info(
            "scheduler_leader_election_starting",
            worker_id=self._worker_id,
            lock_key=self._lock_key,
            lock_ttl_seconds=self._lock_ttl,
        )

        if self._redis is None:
            logger.warning(
                "scheduler_leader_no_redis_fallback",
                worker_id=self._worker_id,
            )
            await self._become_leader()
            return

        if await self._try_acquire():
            return  # _become_leader() already called

        # SETNX failed — log stale lock details for diagnostics
        await self._log_stale_lock_info()

        # Start background re-election
        logger.info(
            "scheduler_leader_starting_re_election",
            worker_id=self._worker_id,
            interval_seconds=self._re_election_interval,
        )
        self._re_election_task = asyncio.create_task(
            self._re_election_loop(),
            name="scheduler-leader-re-election",
        )

    async def shutdown(self) -> None:
        """
        Release leadership, stop scheduler, cancel background tasks.

        Safe to call even if start() was never called or failed (idempotent).
        """
        # Cancel re-election task (if running)
        if self._re_election_task is not None and not self._re_election_task.done():
            self._re_election_task.cancel()
            try:
                await self._re_election_task
            except asyncio.CancelledError:
                pass  # Expected: task was just cancelled above
            logger.debug(
                "scheduler_leader_re_election_cancelled",
                worker_id=self._worker_id,
            )

        was_leader = self._is_leader
        uptime_seconds = (
            round(time.monotonic() - self._elected_at, 1) if self._elected_at is not None else 0.0
        )

        # Stop scheduler and release lock
        if self._is_leader:
            try:
                if self._scheduler.running:
                    self._scheduler.shutdown()
            except Exception as exc:
                logger.error(
                    "scheduler_shutdown_failed",
                    worker_id=self._worker_id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

            # Release lock for fast takeover on restart
            try:
                if self._redis is not None:
                    await self._redis.delete(self._lock_key)
                    logger.debug(
                        "scheduler_leader_lock_deleted",
                        worker_id=self._worker_id,
                    )
            except Exception:
                pass  # Lock will expire via TTL anyway

        logger.info(
            "scheduler_leader_released",
            worker_id=self._worker_id,
            was_leader=was_leader,
            uptime_seconds=uptime_seconds,
        )

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    async def _try_acquire(self) -> bool:
        """
        Single atomic SETNX attempt.

        Returns:
            True if lock was acquired AND _become_leader() succeeded.
            False if lock is held by another worker, Redis unavailable,
            Redis error, or scheduler failed to start (lock released for retry).
        """
        if self._redis is None:
            return False
        try:
            result = await self._redis.set(
                self._lock_key,
                self._worker_id,
                nx=True,
                ex=self._lock_ttl,
            )
            if bool(result):
                await self._become_leader()
                return self._is_leader  # False if _become_leader rolled back
            return False
        except Exception as exc:
            logger.warning(
                "scheduler_leader_acquire_error",
                worker_id=self._worker_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return False

    async def _become_leader(self) -> None:
        """
        Activate as scheduler leader.

        1. Set leader flag and timestamp.
        2. Register lock renewal job on the scheduler.
        3. Start scheduler (if not already running).
        4. Call on_elected callback (protected, non-fatal).

        On any error in steps 1-3, rolls back _is_leader, releases the
        Redis lock (so re-election can retry), and returns without calling
        the callback.
        """
        self._is_leader = True
        self._elected_at = time.monotonic()

        try:
            # Add lock renewal job
            self._scheduler.add_job(
                self._renew_lock,
                trigger="interval",
                seconds=self._renew_interval,
                id=SCHEDULER_JOB_LEADER_LOCK_RENEWAL,
                name="Renew scheduler leader lock",
                replace_existing=True,
            )

            # Start scheduler (guard against double-start)
            if not self._scheduler.running:
                self._scheduler.start()
                jobs_count = len(self._scheduler.get_jobs())
                logger.info(
                    "scheduler_leader_started",
                    worker_id=self._worker_id,
                    jobs_count=jobs_count,
                )
        except Exception as exc:
            self._is_leader = False
            self._elected_at = None
            # Release the lock so re-election loop can retry
            if self._redis is not None:
                try:
                    await self._redis.delete(self._lock_key)
                except Exception:
                    pass  # Lock will expire via TTL
            logger.error(
                "scheduler_leader_become_leader_failed",
                worker_id=self._worker_id,
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )
            return  # Don't call on_elected if scheduler failed

        logger.info(
            "scheduler_leader_elected",
            worker_id=self._worker_id,
            method="immediate" if self._re_election_task is None else "re_election",
        )

        # Call on_elected callback (protected — must not break the scheduler)
        if self._on_elected is not None:
            try:
                await self._on_elected()
            except Exception as exc:
                logger.warning(
                    "scheduler_leader_on_elected_callback_error",
                    worker_id=self._worker_id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

    async def _renew_lock(self) -> None:
        """Renew leader lock TTL. Registered as a scheduler job."""
        try:
            if self._redis is not None:
                await self._redis.expire(self._lock_key, self._lock_ttl)
                logger.debug(
                    "scheduler_leader_lock_renewed",
                    worker_id=self._worker_id,
                    ttl_seconds=self._lock_ttl,
                )
        except Exception as exc:
            logger.warning(
                "scheduler_leader_lock_renewal_failed",
                worker_id=self._worker_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )

    async def _re_election_loop(self) -> None:
        """
        Background task: periodically try to acquire leadership.

        Runs until leadership is acquired or the task is cancelled (shutdown).
        Catches all exceptions to prevent silent task death.
        """
        iteration = 0
        try:
            while not self._is_leader:
                await asyncio.sleep(self._re_election_interval)
                iteration += 1
                logger.debug(
                    "scheduler_leader_re_election_check",
                    worker_id=self._worker_id,
                    iteration=iteration,
                )
                if await self._try_acquire():
                    return  # _become_leader() already called
        except asyncio.CancelledError:
            logger.debug(
                "scheduler_leader_re_election_cancelled",
                worker_id=self._worker_id,
            )
        except Exception as exc:
            logger.error(
                "scheduler_leader_re_election_failed",
                worker_id=self._worker_id,
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )

    async def _log_stale_lock_info(self) -> None:
        """Log diagnostic info about the existing lock holder (best-effort)."""
        try:
            if self._redis is not None:
                lock_holder = await self._redis.get(self._lock_key)
                lock_ttl = await self._redis.ttl(self._lock_key)
                logger.warning(
                    "scheduler_leader_stale_lock_detected",
                    worker_id=self._worker_id,
                    lock_holder=lock_holder,  # str (decode_responses=True)
                    lock_ttl_remaining=lock_ttl,
                )
        except Exception:
            pass  # Best-effort diagnostics
