"""
Scheduled task for automatic interest cleanup.

Performs three cleanup operations:
1. Retro-merge duplicates: case variants and near-identical topics (ADR-131)
2. Mark dormant: Interests with effective_weight < 0.5 for N days
3. Delete dormant: Interests dormant for > N days

Runs daily at configured hour (default: 3 AM UTC).

References:
    - Pattern: memory_cleanup.py
"""

import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_INTEREST_CLEANUP
from src.domains.interests.models import InterestStatus, UserInterest
from src.domains.interests.repository import InterestRepository
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database import get_db_context
from src.infrastructure.locks import SchedulerLock
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)
from src.infrastructure.observability.metrics_registry import interest_merge_total

logger = get_logger(__name__)


def find_duplicate_pairs(
    interests: list[UserInterest],
    threshold: float,
) -> list[tuple[UserInterest, UserInterest]]:
    """Find (keep, dup) merge pairs among one user's active interests.

    A pair is a duplicate when topics match case/whitespace-insensitively, or
    when both embeddings exist and cosine similarity >= threshold. The kept
    side has the higher positive_signals (tie: earlier created_at). Chains
    collapse onto a single winner via union-find-lite resolution.

    Args:
        interests: One user's active interests.
        threshold: Cosine threshold (settings.interest_merge_similarity_threshold;
            >= 0.95 is the only reliable zone for these embeddings — prod
            evidence: true duplicate at 0.987, first false pair at 0.890).

    Returns:
        Ordered (keep, dup) pairs, safe to merge sequentially.
    """
    from src.infrastructure.llm.local_embeddings import cosine_similarity

    def rank(interest: UserInterest) -> tuple[int, float]:
        return (-interest.positive_signals, interest.created_at.timestamp())

    winner: dict[int, UserInterest] = {id(i): i for i in interests}

    def resolve(interest: UserInterest) -> UserInterest:
        seen = interest
        while winner[id(seen)] is not seen:
            seen = winner[id(seen)]
        return seen

    ordered = sorted(interests, key=rank)
    for pos, first in enumerate(ordered):
        for second in ordered[pos + 1 :]:
            same_text = first.topic.strip().lower() == second.topic.strip().lower()
            same_vector = (
                first.embedding is not None
                and second.embedding is not None
                and cosine_similarity(first.embedding, second.embedding) >= threshold
            )
            if same_text or same_vector:
                keep, dup = resolve(first), resolve(second)
                if keep is not dup:
                    winner[id(dup)] = keep

    pairs: list[tuple[UserInterest, UserInterest]] = []
    for interest in ordered:
        keep = resolve(interest)
        if keep is not interest:
            pairs.append((keep, interest))
    return pairs


async def merge_duplicate_interests(repo: InterestRepository, threshold: float) -> int:
    """Retro-merge duplicate active interests across all users (ADR-131).

    Args:
        repo: InterestRepository bound to the job's session.
        threshold: Cosine similarity threshold for near-duplicates.

    Returns:
        Number of interests merged away.
    """
    merged_count = 0
    user_rows = await repo.db.execute(
        select(UserInterest.user_id)
        .where(UserInterest.status == InterestStatus.ACTIVE.value)
        .distinct()
    )
    for (user_id,) in user_rows.all():
        actives = await repo.get_active_for_user(user_id)
        for keep, dup in find_duplicate_pairs(actives, threshold=threshold):
            await repo.merge_interests(keep, dup)
            merged_count += 1
            interest_merge_total.inc()
    return merged_count


async def mark_dormant_interests(
    repo: InterestRepository,
    threshold_days: int,
    decay_rate: float,
    now: datetime,
) -> int:
    """
    Mark interests as dormant if their effective weight has been below 0.5
    for more than threshold_days.

    An interest becomes dormant when:
    1. Status is ACTIVE
    2. Effective weight < 0.5
    3. Time since last_mentioned_at > threshold_days

    Args:
        repo: InterestRepository instance
        threshold_days: Days below threshold before marking dormant
        decay_rate: Weight decay rate per day
        now: Current datetime

    Returns:
        Number of interests marked dormant
    """
    dormant_count = 0

    # Query all active interests directly (across all users)
    result = await repo.db.execute(
        select(UserInterest).where(UserInterest.status == InterestStatus.ACTIVE.value)
    )
    active_interests = list(result.scalars().all())

    threshold_date = now - timedelta(days=threshold_days)

    for interest in active_interests:
        # Calculate effective weight
        effective_weight = repo.calculate_effective_weight(
            interest, decay_rate_per_day=decay_rate, now=now
        )

        # Check if weight has been below 0.5 and not mentioned recently
        if effective_weight < 0.5 and interest.last_mentioned_at < threshold_date:
            await repo.mark_dormant(interest, now=now)
            dormant_count += 1

            logger.debug(
                "interest_marked_dormant",
                interest_id=str(interest.id),
                user_id=str(interest.user_id),
                topic=interest.topic[:50],
                effective_weight=round(effective_weight, 3),
                days_since_mention=(now - interest.last_mentioned_at).days,
            )

    return dormant_count


async def cleanup_interests() -> dict[str, Any]:
    """
    Daily interest cleanup job.

    Performs two cleanup operations:
    1. Mark dormant: Active interests with low weight for too long
    2. Delete dormant: Dormant interests older than deletion threshold

    Metrics:
        - background_job_duration_seconds{job_name="interest_cleanup"}
        - background_job_errors_total{job_name="interest_cleanup"}

    Returns:
        Stats dict with marked_dormant, deleted, total_checked
    """
    # Acquire distributed lock to prevent duplicate execution across workers
    redis = await get_redis_cache()
    if redis:
        async with SchedulerLock(redis, SCHEDULER_JOB_INTEREST_CLEANUP) as lock:
            if not lock.acquired:
                return {"status": "skipped", "reason": "lock_busy"}

    start_time = time.perf_counter()
    job_name = SCHEDULER_JOB_INTEREST_CLEANUP

    stats: dict[str, Any] = {
        "merged": 0,
        "marked_dormant": 0,
        "deleted": 0,
        "total_checked": 0,
        "errors": 0,
    }

    try:
        now = datetime.now(UTC)

        # Get config from settings
        dormant_threshold_days = settings.interest_dormant_threshold_days
        deletion_threshold_days = settings.interest_deletion_threshold_days
        decay_rate = settings.interest_decay_rate_per_day

        logger.info(
            "interest_cleanup_started",
            dormant_threshold_days=dormant_threshold_days,
            deletion_threshold_days=deletion_threshold_days,
            decay_rate=decay_rate,
        )

        async with get_db_context() as db:
            repo = InterestRepository(db)

            # Count total interests for stats
            all_interests = await db.execute(select(UserInterest))
            stats["total_checked"] = len(list(all_interests.scalars().all()))

            # Step 0: Retro-merge duplicates BEFORE dormancy so merged
            # signals count toward the kept interest's weight (ADR-131).
            stats["merged"] = await merge_duplicate_interests(
                repo=repo,
                threshold=settings.interest_merge_similarity_threshold,
            )

            # Step 1: Mark dormant interests
            stats["marked_dormant"] = await mark_dormant_interests(
                repo=repo,
                threshold_days=dormant_threshold_days,
                decay_rate=decay_rate,
                now=now,
            )

            # Step 2: Delete old dormant interests
            stats["deleted"] = await repo.delete_dormant_older_than(
                days=deletion_threshold_days,
                now=now,
            )

            # Commit all changes
            await db.commit()

        # Track duration
        duration = time.perf_counter() - start_time
        background_job_duration_seconds.labels(job_name=job_name).observe(duration)

        logger.info(
            "interest_cleanup_completed",
            total_checked=stats["total_checked"],
            merged=stats["merged"],
            marked_dormant=stats["marked_dormant"],
            deleted=stats["deleted"],
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
            "interest_cleanup_failed",
            error=str(e),
            error_type=type(e).__name__,
            duration_seconds=round(duration, 3),
            exc_info=True,
        )
        raise
