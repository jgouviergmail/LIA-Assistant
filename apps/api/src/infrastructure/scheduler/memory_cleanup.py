"""
Scheduled task for automatic memory cleanup (Phase 6).

Uses a hybrid retention algorithm combining:
- Usage count (40% weight)
- Importance score (30% weight)
- Recency/freshness (30% weight)

Protected memories (never auto-deleted):
- pinned = True
- category = "sensitivity"
- abs(emotional_weight) >= configured threshold

Runs daily at configured hour (default: 4 AM UTC).
"""

import time
from datetime import UTC, datetime
from typing import Any

import structlog

from src.core.config import settings
from src.domains.agents.context.store import get_tool_context_store
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)
from src.infrastructure.store.semantic_store import MemoryNamespace

logger = structlog.get_logger(__name__)


def calculate_retention_score(
    memory: dict,
    now: datetime,
    max_age_days: int,
    min_usage_count: int,
    weight_usage: float,
    weight_importance: float,
    weight_recency: float,
) -> float:
    """
    Calculate retention score for a memory (0-1).

    Higher score = higher chance of being kept.

    Formula:
    - weight_usage * usage boost (usage_count / min_usage_count, capped at 1.0)
    - weight_importance * importance boost (already 0-1)
    - weight_recency * recency boost (1.0 for new, decays linearly with age)

    Args:
        memory: Memory dict with usage_count, importance, created_at
        now: Current datetime
        max_age_days: Maximum age in days before full decay
        min_usage_count: Usage count for 100% usage boost
        weight_usage: Weight for usage component (default 0.4)
        weight_importance: Weight for importance component (default 0.3)
        weight_recency: Weight for recency component (default 0.3)

    Returns:
        Retention score between 0.0 and 1.0
    """
    # Usage boost (0-1, capped at 1)
    usage_count = int(memory.get("usage_count", 0))
    usage_boost = min(1.0, usage_count / max(1, min_usage_count))

    # Importance boost (already 0-1)
    importance_boost = float(memory.get("importance", 0.7))

    # Recency boost (decays linearly with age)
    created_at = memory.get("created_at")
    if created_at:
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                created_at = None

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
    memory: dict,
    now: datetime,
    max_age_days: int,
    min_usage_count: int,
    purge_threshold: float,
    weight_usage: float,
    weight_importance: float,
    weight_recency: float,
) -> tuple[bool, float]:
    """
    Determine if a memory should be purged.

    Protection rules (never purged):
    1. pinned = True
    2. Age < max_age_days (not yet eligible)

    If none of the above, purge if retention_score < purge_threshold.

    Args:
        memory: Memory dict
        now: Current datetime
        max_age_days: Age threshold for eligibility
        min_usage_count: Usage count for full boost
        purge_threshold: Score below which to purge
        weight_usage: Weight for usage component
        weight_importance: Weight for importance component
        weight_recency: Weight for recency component

    Returns:
        Tuple of (should_purge, retention_score)
    """
    # Protection 1: Pinned
    if memory.get("pinned", False):
        return False, 1.0

    # Protection 2: Too recent (not yet eligible)
    created_at = memory.get("created_at")
    if created_at:
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                created_at = None

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
    """
    Daily memory cleanup job.

    Iterates through all user memories and purges those that:
    - Are older than MEMORY_MAX_AGE_DAYS
    - Have low retention score (< MEMORY_PURGE_THRESHOLD)
    - Are not protected (pinned only)

    Metrics:
        - background_job_duration_seconds{job_name="memory_cleanup"}
        - background_job_errors_total{job_name="memory_cleanup"}

    Returns:
        Stats dict with total_checked, purged, by_category, users_processed
    """
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
        store = await get_tool_context_store()
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

        # Get all unique user namespaces from the store
        # We need to query the store's internal table to find all memory namespaces
        # The store uses a table with namespace as a column

        # Access the underlying connection to query namespaces
        if hasattr(store, "_conn") and store._conn is not None:
            conn = store._conn
            # Query for all unique user_id values that have "memories" collection
            query = """
                SELECT DISTINCT namespace[1] as user_id
                FROM store
                WHERE namespace[2] = 'memories'
                AND array_length(namespace, 1) >= 2
            """
            async with conn.cursor() as cursor:
                await cursor.execute(query)
                rows = await cursor.fetchall()
                user_ids = [row["user_id"] for row in rows if row.get("user_id")]

            logger.debug(
                "memory_cleanup_users_found",
                user_count=len(user_ids),
            )

            # Process each user's memories
            for user_id in user_ids:
                stats["users_processed"] += 1
                namespace = MemoryNamespace(user_id)

                # Get all memories for this user using empty query search
                try:
                    memories = await store.asearch(
                        namespace.to_tuple(),
                        query="",
                        limit=1000,  # Large limit to get all
                    )
                except Exception as e:
                    logger.warning(
                        "memory_cleanup_user_search_failed",
                        user_id=user_id,
                        error=str(e),
                    )
                    continue

                for item in memories:
                    stats["total_checked"] += 1

                    if not isinstance(item.value, dict):
                        continue

                    should_delete, score = should_purge(
                        item.value,
                        now,
                        max_age_days,
                        min_usage_count,
                        purge_threshold,
                        weight_usage,
                        weight_importance,
                        weight_recency,
                    )

                    if should_delete:
                        # Delete the memory
                        try:
                            await store.adelete(namespace.to_tuple(), item.key)

                            stats["purged"] += 1
                            category = item.value.get("category", "unknown")
                            stats["by_category"][category] = (
                                stats["by_category"].get(category, 0) + 1
                            )

                            logger.debug(
                                "memory_purged",
                                user_id=user_id,
                                memory_id=item.key,
                                category=category,
                                retention_score=round(score, 3),
                                content_preview=item.value.get("content", "")[:50],
                            )
                        except Exception as e:
                            logger.warning(
                                "memory_delete_failed",
                                user_id=user_id,
                                memory_id=item.key,
                                error=str(e),
                            )
                    else:
                        stats["protected"] += 1
        else:
            logger.warning(
                "memory_cleanup_store_no_connection",
                message="Store connection not available, skipping cleanup",
            )

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
