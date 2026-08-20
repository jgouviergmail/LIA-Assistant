"""
Scheduled task for automatic memory cleanup (Phase 6).

Retention formula:
    score = weight_importance * importance + weight_recency * recency_factor
    recency_factor = max(0, 1 - age_days / recency_decay_days)

Negative penalty: if usage_count == 0 and age_days > usage_penalty_age_days,
    score *= usage_penalty_factor
This treats usage_count strictly as a negative signal (never-activated memories
are suspect), avoiding the false-positive bias of counting semantic retrieval
as actual utility.

Protected memories (never auto-deleted):
- pinned = True (user-locked)
- Age < min_age_for_cleanup_days (grace period, not yet eligible)

Runs daily at configured hour (default: 4 AM UTC).

Phase: v1.14.0 — Migrated from LangGraph store to PostgreSQL custom
"""

import time
from datetime import UTC, datetime
from typing import Any

import structlog

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_MEMORY_CLEANUP
from src.domains.memories.retention import should_purge
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.locks import SchedulerLock
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)

logger = structlog.get_logger(__name__)


async def _purge_invalidated_trail() -> int:
    """Purge invalidated rows past retention (Lot 2-B1, ADR-235). Own session."""
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        from src.domains.memories.repository import MemoryRepository

        return await MemoryRepository(db).delete_invalidated_older_than(
            days=settings.memory_invalidated_retention_days
        )


async def cleanup_memories() -> dict[str, Any]:
    """Daily memory cleanup job.

    Iterates through all user memories and purges those that:
    - Are past the grace period (MEMORY_MIN_AGE_FOR_CLEANUP_DAYS)
    - Have a retention score < MEMORY_PURGE_THRESHOLD
    - Are not pinned (user-locked)

    Metrics:
        - background_job_duration_seconds{job_name="memory_cleanup"}
        - background_job_errors_total{job_name="memory_cleanup"}

    Returns:
        Stats dict with total_checked, purged, by_category, users_processed.
    """
    from src.infrastructure.database.session import get_db_context

    # Acquire distributed lock to prevent duplicate execution across workers
    redis = await get_redis_cache()
    if redis:
        async with SchedulerLock(redis, SCHEDULER_JOB_MEMORY_CLEANUP) as lock:
            if not lock.acquired:
                return {"status": "skipped", "reason": "lock_busy"}

    start_time = time.perf_counter()
    job_name = "memory_cleanup"

    stats: dict[str, Any] = {
        "total_checked": 0,
        "purged": 0,
        "protected": 0,
        "by_category": {},
        "users_processed": 0,
        "invalidated_purged": 0,
    }

    try:
        now = datetime.now(UTC)

        # Lot 2-B1 (ADR-235): purge the stale supersession trail first —
        # invalidated rows past the retention window, all users, one DELETE.
        stats["invalidated_purged"] = await _purge_invalidated_trail()

        # Get config from settings
        min_age_for_cleanup_days = settings.memory_min_age_for_cleanup_days
        recency_decay_days = settings.memory_recency_decay_days
        usage_penalty_age_days = settings.memory_usage_penalty_age_days
        usage_penalty_factor = settings.memory_usage_penalty_factor
        purge_threshold = settings.memory_purge_threshold
        weight_importance = settings.memory_retention_weight_importance
        weight_recency = settings.memory_retention_weight_recency

        logger.info(
            "memory_cleanup_started",
            min_age_for_cleanup_days=min_age_for_cleanup_days,
            recency_decay_days=recency_decay_days,
            usage_penalty_age_days=usage_penalty_age_days,
            usage_penalty_factor=usage_penalty_factor,
            purge_threshold=purge_threshold,
            weight_importance=weight_importance,
            weight_recency=weight_recency,
        )

        async with get_db_context() as db:
            from src.domains.memories.repository import MemoryRepository

            repo = MemoryRepository(db)

            # Get all user IDs that have memories
            user_ids = await repo.get_user_ids_with_memories()

            logger.debug(
                "memory_cleanup_users_found",
                user_count=len(user_ids),
            )

            # Process each user's memories
            for user_id in user_ids:
                stats["users_processed"] += 1

                try:
                    # Get non-pinned memories for cleanup evaluation
                    memories = await repo.get_for_cleanup(
                        user_id=user_id,
                        min_age_for_cleanup_days=min_age_for_cleanup_days,
                    )
                except Exception as e:
                    logger.warning(
                        "memory_cleanup_user_search_failed",
                        user_id=str(user_id),
                        error=str(e),
                    )
                    continue

                for memory in memories:
                    stats["total_checked"] += 1

                    should_delete, score = should_purge(
                        memory,
                        now,
                        min_age_for_cleanup_days,
                        recency_decay_days,
                        usage_penalty_age_days,
                        usage_penalty_factor,
                        purge_threshold,
                        weight_importance,
                        weight_recency,
                    )

                    if should_delete:
                        try:
                            await repo.delete(memory)

                            stats["purged"] += 1
                            category = memory.category or "unknown"
                            stats["by_category"][category] = (
                                stats["by_category"].get(category, 0) + 1
                            )

                            logger.debug(
                                "memory_purged",
                                user_id=str(user_id),
                                memory_id=str(memory.id),
                                category=category,
                                retention_score=round(score, 3),
                                content_preview=(memory.content or "")[:50],
                            )
                        except Exception as e:
                            logger.warning(
                                "memory_delete_failed",
                                user_id=str(user_id),
                                memory_id=str(memory.id),
                                error=str(e),
                            )
                    else:
                        stats["protected"] += 1

            await db.commit()

        # Track duration
        duration = time.perf_counter() - start_time
        background_job_duration_seconds.labels(job_name=job_name).observe(duration)

        logger.info(
            "memory_cleanup_completed",
            total_checked=stats["total_checked"],
            purged=stats["purged"],
            protected=stats["protected"],
            users_processed=stats["users_processed"],
            by_category=stats["by_category"],
            duration_seconds=round(duration, 3),
        )

        return stats

    except Exception as e:
        # Track error
        background_job_errors_total.labels(job_name=job_name).inc()

        # Track duration even on error
        duration = time.perf_counter() - start_time
        background_job_duration_seconds.labels(job_name=job_name).observe(duration)

        logger.exception(
            "memory_cleanup_failed",
            error_type=type(e).__name__,
            duration_seconds=round(duration, 3),
        )
        raise
