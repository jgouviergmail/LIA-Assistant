"""
Scheduled task for automatic cleanup of unverified accounts.

Deletes non-OAuth accounts that:
- Have is_verified = False
- Have is_active = False
- Were created more than UNVERIFIED_ACCOUNT_CLEANUP_DAYS ago (default: 1 day)

OAuth accounts are never deleted by this job (they don't have password-based verification).

Runs daily at configured hour (default: 5 AM UTC).
"""

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from src.core.constants import (
    SCHEDULER_JOB_UNVERIFIED_CLEANUP,
    UNVERIFIED_ACCOUNT_CLEANUP_DAYS,
)
from src.domains.users.resource_release import build_capability_origin_scrub
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database.session import get_db_context
from src.infrastructure.locks import SchedulerLock
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)

logger = structlog.get_logger(__name__)


async def cleanup_unverified_accounts() -> dict[str, Any]:
    """
    Daily unverified account cleanup job.

    Deletes non-OAuth accounts that have not verified their email
    within UNVERIFIED_ACCOUNT_CLEANUP_DAYS (default: 1 day).

    Protection rules (never deleted):
    1. OAuth accounts (oauth_provider is not None)
    2. Verified accounts (is_verified = True)
    3. Active accounts (is_active = True)
    4. Accounts created less than UNVERIFIED_ACCOUNT_CLEANUP_DAYS ago

    Metrics:
        - background_job_duration_seconds{job_name="unverified_account_cleanup"}
        - background_job_errors_total{job_name="unverified_account_cleanup"}

    Returns:
        Stats dict with total_checked, deleted, cutoff_datetime
    """
    # Acquire distributed lock to prevent duplicate execution across workers
    redis = await get_redis_cache()
    if redis:
        async with SchedulerLock(redis, SCHEDULER_JOB_UNVERIFIED_CLEANUP) as lock:
            if not lock.acquired:
                return {"status": "skipped", "reason": "lock_busy"}

    start_time = time.perf_counter()
    job_name = "unverified_account_cleanup"

    stats: dict[str, Any] = {
        "total_checked": 0,
        "deleted": 0,
        "cutoff_datetime": None,
    }

    try:
        # Import here to avoid circular imports
        from sqlalchemy import delete, select
        from sqlalchemy.sql import func

        from src.domains.users.models import User

        # Calculate cutoff datetime
        cutoff = datetime.now(UTC) - timedelta(days=UNVERIFIED_ACCOUNT_CLEANUP_DAYS)
        stats["cutoff_datetime"] = cutoff.isoformat()

        logger.info(
            "unverified_account_cleanup_started",
            cutoff_datetime=cutoff.isoformat(),
            cleanup_days=UNVERIFIED_ACCOUNT_CLEANUP_DAYS,
        )

        async with get_db_context() as session:
            # First, count and log the accounts to be deleted
            eligible = (
                User.is_verified.is_(False)
                & User.is_active.is_(False)
                & User.oauth_provider.is_(None)
                & (User.created_at < cutoff)
            )
            count_query = select(func.count(User.id)).where(eligible)
            result = await session.execute(count_query)
            stats["total_checked"] = result.scalar() or 0

            if stats["total_checked"] == 0:
                logger.info(
                    "unverified_account_cleanup_no_accounts",
                    message="No unverified accounts to delete",
                    cutoff_datetime=cutoff.isoformat(),
                )
            else:
                # Delete the accounts. Their addresses are neither read nor
                # logged: a line above DEBUG carries the count (ADR-317), like
                # the demo account purge — they used to be logged at INFO, cut
                # to three characters and the whole domain.
                delete_query = delete(User).where(eligible)
                await session.execute(
                    build_capability_origin_scrub(select(User.id).where(eligible))
                )
                delete_result = await session.execute(delete_query)
                await session.commit()

                stats["deleted"] = delete_result.rowcount  # type: ignore[attr-defined]

                logger.info(
                    "unverified_accounts_deleted",
                    count=stats["deleted"],
                    cutoff_datetime=cutoff.isoformat(),
                )

        # Track duration
        duration = time.perf_counter() - start_time
        background_job_duration_seconds.labels(job_name=job_name).observe(duration)

        logger.info(
            "unverified_account_cleanup_completed",
            total_checked=stats["total_checked"],
            deleted=stats["deleted"],
            cutoff_datetime=stats["cutoff_datetime"],
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
            "unverified_account_cleanup_failed",
            error=str(e),
            error_type=type(e).__name__,
            duration_seconds=round(duration, 3),
        )
        raise
