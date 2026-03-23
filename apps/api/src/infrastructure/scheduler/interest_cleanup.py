"""
Scheduled task for automatic interest cleanup.

Performs two cleanup operations:
1. Mark dormant: Interests with effective_weight < 0.5 for N days
2. Delete dormant: Interests dormant for > N days

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

logger = get_logger(__name__)


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
