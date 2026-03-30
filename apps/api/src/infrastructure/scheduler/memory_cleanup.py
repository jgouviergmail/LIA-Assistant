"""
Scheduled task for automatic memory cleanup (Phase 6).

Uses a hybrid retention algorithm combining:
- Usage count (40% weight)
- Importance score (30% weight)
- Recency/freshness (30% weight)

Protected memories (never auto-deleted):
- pinned = True
- Age < max_age_days (not yet eligible)

Runs daily at configured hour (default: 4 AM UTC).

Phase: v1.14.0 — Migrated from LangGraph store to PostgreSQL custom
"""

import time
from datetime import UTC, datetime
from typing import Any

import structlog

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_MEMORY_CLEANUP
from src.domains.memories.models import Memory
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.locks import SchedulerLock
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)

logger = structlog.get_logger(__name__)


def calculate_retention_score(
    memory: Memory,
    now: datetime,
    max_age_days: int,
    min_usage_count: int,
    weight_usage: float,
    weight_importance: float,
    weight_recency: float,
) -> float:
    """Calculate retention score for a memory (0-1).

    Higher score = higher chance of being kept.

    Formula:
    - weight_usage * usage boost (usage_count / min_usage_count, capped at 1.0)
    - weight_importance * importance boost (already 0-1)
    - weight_recency * recency boost (1.0 for new, decays linearly with age)

    Args:
        memory: Memory ORM object.
        now: Current datetime.
        max_age_days: Maximum age in days before full decay.
        min_usage_count: Usage count for 100% usage boost.
        weight_usage: Weight for usage component (default 0.4).
        weight_importance: Weight for importance component (default 0.3).
        weight_recency: Weight for recency component (default 0.3).

    Returns:
        Retention score between 0.0 and 1.0.
    """
    # Usage boost (0-1, capped at 1)
    usage_count = memory.usage_count or 0
    usage_boost = min(1.0, usage_count / max(1, min_usage_count))

    # Importance boost (already 0-1)
    importance_boost = memory.importance or 0.7

    # Recency boost (decays linearly with age)
    created_at = memory.created_at
    if created_at:
        age_days = (now - created_at).days
        recency_boost = max(0.0, 1.0 - age_days / max(1, max_age_days))
    else:
        recency_boost = 0.5  # Default if no date

    # Weighted score
    return float(
        weight_usage * usage_boost
        + weight_importance * importance_boost
        + weight_recency * recency_boost
    )


def should_purge(
    memory: Memory,
    now: datetime,
    max_age_days: int,
    min_usage_count: int,
    purge_threshold: float,
    weight_usage: float,
    weight_importance: float,
    weight_recency: float,
) -> tuple[bool, float]:
    """Determine if a memory should be purged.

    Protection rules (never purged):
    1. pinned = True
    2. Age < max_age_days (not yet eligible)

    If none of the above, purge if retention_score < purge_threshold.

    Args:
        memory: Memory ORM object.
        now: Current datetime.
        max_age_days: Age threshold for eligibility.
        min_usage_count: Usage count for full boost.
        purge_threshold: Score below which to purge.
        weight_usage: Weight for usage component.
        weight_importance: Weight for importance component.
        weight_recency: Weight for recency component.

    Returns:
        Tuple of (should_purge, retention_score).
    """
    # Protection 1: Pinned
    if memory.pinned:
        return False, 1.0

    # Protection 2: Too recent (not yet eligible)
    created_at = memory.created_at
    if created_at:
        age_days = (now - created_at).days
        if age_days < max_age_days:
            return False, 1.0  # Not yet eligible

    # Calculate retention score
    retention_score = calculate_retention_score(
        memory,
        now,
        max_age_days,
        min_usage_count,
        weight_usage,
        weight_importance,
        weight_recency,
    )

    return retention_score < purge_threshold, retention_score


async def cleanup_memories() -> dict[str, Any]:
    """Daily memory cleanup job.

    Iterates through all user memories and purges those that:
    - Are older than MEMORY_MAX_AGE_DAYS
    - Have low retention score (< MEMORY_PURGE_THRESHOLD)
    - Are not protected (pinned only)

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
    }

    try:
        now = datetime.now(UTC)

        # Get config from settings
        max_age_days = settings.memory_max_age_days
        min_usage_count = settings.memory_min_usage_count
        purge_threshold = settings.memory_purge_threshold
        weight_usage = settings.memory_retention_weight_usage
        weight_importance = settings.memory_retention_weight_importance
        weight_recency = settings.memory_retention_weight_recency

        logger.info(
            "memory_cleanup_started",
            max_age_days=max_age_days,
            min_usage_count=min_usage_count,
            purge_threshold=purge_threshold,
            weight_usage=weight_usage,
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
                        max_age_days=max_age_days,
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
                        max_age_days,
                        min_usage_count,
                        purge_threshold,
                        weight_usage,
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

        logger.error(
            "memory_cleanup_failed",
            error=str(e),
            error_type=type(e).__name__,
            duration_seconds=round(duration, 3),
        )
        raise
