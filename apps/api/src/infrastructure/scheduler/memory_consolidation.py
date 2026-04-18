"""
Scheduled task for daily memory consolidation.

Merges near-duplicate memory pairs that escaped the extraction-time dedup
(typically when a user rephrases an existing fact with enough semantic
divergence that the dedup search missed it). Runs after memory_cleanup
so the table is pruned before consolidation.

Survivor selection (deterministic, no usage_count):
    1. Higher importance wins.
    2. Tie → longer content wins (completeness proxy).
    3. Tie → more recent created_at wins (fresher info).

Skip rules (no merge):
- Either memory is pinned (handled at SQL level in find_consolidation_pairs).
- Categories differ (preserving semantic intent over proximity).
- |emotional_weight_a - emotional_weight_b| > emotional_diff_skip
  (affect divergence indicates distinct experiences despite wording overlap).

Observability:
- Metrics: background_job_duration_seconds, background_job_errors_total
- Structured logs: per-pair decisions (merged, skipped_category, skipped_emotional)
"""

import time
from typing import Any

import structlog

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_MEMORY_CONSOLIDATION
from src.domains.memories.models import Memory
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.locks import SchedulerLock
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)

logger = structlog.get_logger(__name__)


def _pick_survivor(mem_a: Memory, mem_b: Memory) -> tuple[Memory, Memory]:
    """Choose which memory to keep and which to delete.

    Deterministic cascade: importance > completeness > recency.

    Args:
        mem_a: First memory (never pinned, enforced by SQL).
        mem_b: Second memory (never pinned, enforced by SQL).

    Returns:
        Tuple of (survivor, loser).
    """
    imp_a = mem_a.importance or 0.7
    imp_b = mem_b.importance or 0.7
    if imp_a != imp_b:
        return (mem_a, mem_b) if imp_a > imp_b else (mem_b, mem_a)

    len_a = len(mem_a.content or "")
    len_b = len(mem_b.content or "")
    if len_a != len_b:
        return (mem_a, mem_b) if len_a > len_b else (mem_b, mem_a)

    # Fallback: most recent created_at wins. Defensive guard if one is None.
    created_a = mem_a.created_at
    created_b = mem_b.created_at
    if created_a is None:
        return mem_b, mem_a
    if created_b is None:
        return mem_a, mem_b
    return (mem_a, mem_b) if created_a >= created_b else (mem_b, mem_a)


def _should_skip(
    mem_a: Memory,
    mem_b: Memory,
    emotional_diff_skip: int,
) -> str | None:
    """Return a reason string if the pair must be skipped, else None.

    Args:
        mem_a: First memory.
        mem_b: Second memory.
        emotional_diff_skip: Absolute emotional_weight gap beyond which
            the pair is treated as distinct experiences.

    Returns:
        "categories_differ", "emotional_diff", or None.
    """
    if (mem_a.category or "") != (mem_b.category or ""):
        return "categories_differ"

    weight_a = mem_a.emotional_weight or 0
    weight_b = mem_b.emotional_weight or 0
    if abs(weight_a - weight_b) > emotional_diff_skip:
        return "emotional_diff"

    return None


async def consolidate_memories() -> dict[str, Any]:
    """Daily memory consolidation job.

    For each user with memories, finds near-duplicate pairs above the
    similarity threshold, applies skip rules, and deletes the loser of
    each surviving pair.

    Metrics:
        - background_job_duration_seconds{job_name="memory_consolidation"}
        - background_job_errors_total{job_name="memory_consolidation"}

    Returns:
        Stats dict with pairs_found, merges_applied, skipped counters,
        users_processed, duration_seconds.
    """
    from src.infrastructure.database.session import get_db_context

    # Distributed lock to prevent concurrent runs across workers.
    redis = await get_redis_cache()
    if redis:
        async with SchedulerLock(redis, SCHEDULER_JOB_MEMORY_CONSOLIDATION) as lock:
            if not lock.acquired:
                return {"status": "skipped", "reason": "lock_busy"}

    if not settings.memory_consolidation_enabled:
        logger.info("memory_consolidation_skipped", reason="disabled_by_flag")
        return {"status": "skipped", "reason": "disabled"}

    start_time = time.perf_counter()
    job_name = "memory_consolidation"

    stats: dict[str, Any] = {
        "pairs_found": 0,
        "merges_applied": 0,
        "skipped_categories_differ": 0,
        "skipped_emotional_diff": 0,
        "skipped_already_consumed": 0,
        "users_processed": 0,
    }

    try:
        similarity_threshold = settings.memory_consolidation_similarity_threshold
        max_pairs = settings.memory_consolidation_max_pairs_per_user
        emotional_diff_skip = settings.memory_consolidation_emotional_diff_skip

        logger.info(
            "memory_consolidation_started",
            similarity_threshold=similarity_threshold,
            max_pairs_per_user=max_pairs,
            emotional_diff_skip=emotional_diff_skip,
        )

        async with get_db_context() as db:
            from src.domains.memories.repository import MemoryRepository

            repo = MemoryRepository(db)
            user_ids = await repo.get_user_ids_with_memories()

            logger.debug(
                "memory_consolidation_users_found",
                user_count=len(user_ids),
            )

            for user_id in user_ids:
                stats["users_processed"] += 1

                try:
                    pairs = await repo.find_consolidation_pairs(
                        user_id=user_id,
                        similarity_threshold=similarity_threshold,
                        limit=max_pairs,
                    )
                except Exception as e:
                    logger.warning(
                        "memory_consolidation_user_search_failed",
                        user_id=str(user_id),
                        error=str(e),
                    )
                    continue

                # Track IDs already consumed in this run. A given memory must
                # not be merged more than once per run: once it is merged into
                # a survivor, subsequent pairs referencing it are stale.
                consumed_ids: set[str] = set()

                for mem_a, mem_b, similarity in pairs:
                    stats["pairs_found"] += 1

                    if str(mem_a.id) in consumed_ids or str(mem_b.id) in consumed_ids:
                        stats["skipped_already_consumed"] += 1
                        continue

                    skip_reason = _should_skip(mem_a, mem_b, emotional_diff_skip)
                    if skip_reason == "categories_differ":
                        stats["skipped_categories_differ"] += 1
                        logger.debug(
                            "memory_pair_skipped",
                            user_id=str(user_id),
                            reason=skip_reason,
                            memory_a=str(mem_a.id),
                            memory_b=str(mem_b.id),
                            similarity=round(similarity, 3),
                        )
                        continue
                    if skip_reason == "emotional_diff":
                        stats["skipped_emotional_diff"] += 1
                        logger.debug(
                            "memory_pair_skipped",
                            user_id=str(user_id),
                            reason=skip_reason,
                            memory_a=str(mem_a.id),
                            memory_b=str(mem_b.id),
                            similarity=round(similarity, 3),
                        )
                        continue

                    survivor, loser = _pick_survivor(mem_a, mem_b)

                    try:
                        await repo.delete(loser)
                        stats["merges_applied"] += 1
                        consumed_ids.add(str(loser.id))

                        logger.info(
                            "memory_pair_consolidated",
                            user_id=str(user_id),
                            survivor_id=str(survivor.id),
                            loser_id=str(loser.id),
                            category=survivor.category,
                            similarity=round(similarity, 3),
                            survivor_importance=round(survivor.importance or 0.7, 2),
                            loser_content_preview=(loser.content or "")[:60],
                        )
                    except Exception as e:
                        logger.warning(
                            "memory_pair_consolidation_failed",
                            user_id=str(user_id),
                            memory_a=str(mem_a.id),
                            memory_b=str(mem_b.id),
                            error=str(e),
                        )

            await db.commit()

        duration = time.perf_counter() - start_time
        background_job_duration_seconds.labels(job_name=job_name).observe(duration)

        logger.info(
            "memory_consolidation_completed",
            pairs_found=stats["pairs_found"],
            merges_applied=stats["merges_applied"],
            skipped_categories_differ=stats["skipped_categories_differ"],
            skipped_emotional_diff=stats["skipped_emotional_diff"],
            skipped_already_consumed=stats["skipped_already_consumed"],
            users_processed=stats["users_processed"],
            duration_seconds=round(duration, 3),
        )

        return stats

    except Exception as e:
        background_job_errors_total.labels(job_name=job_name).inc()

        duration = time.perf_counter() - start_time
        background_job_duration_seconds.labels(job_name=job_name).observe(duration)

        logger.exception(
            "memory_consolidation_failed",
            error_type=type(e).__name__,
            duration_seconds=round(duration, 3),
        )
        raise
