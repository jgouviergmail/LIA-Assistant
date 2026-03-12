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

from src.core.constants import UNVERIFIED_ACCOUNT_CLEANUP_DAYS
from src.infrastructure.database.session import get_db_session
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
    start_time = time.perf_counter()
    job_name = "unverified_account_cleanup"

    stats: dict[str, Any] = {
        "total_checked": 0,
        "deleted": 0,
        "deleted_emails": [],
        "cutoff_datetime": None,
    }

    try:
        # Import here to avoid circular imports
        from sqlalchemy import delete, select
        from sqlalchemy.sql import func

        from src.domains.auth.models import User

        # Calculate cutoff datetime
        cutoff = datetime.now(UTC) - timedelta(days=UNVERIFIED_ACCOUNT_CLEANUP_DAYS)
        stats["cutoff_datetime"] = cutoff.isoformat()

        logger.info(
            "unverified_account_cleanup_started",
            cutoff_datetime=cutoff.isoformat(),
            cleanup_days=UNVERIFIED_ACCOUNT_CLEANUP_DAYS,
        )

        async for session in get_db_session():
            # First, count and log the accounts to be deleted
            count_query = select(func.count(User.id)).where(
                User.is_verified.is_(False),
                User.is_active.is_(False),
                User.oauth_provider.is_(None),  # Not OAuth
                User.created_at < cutoff,
            )
            result = await session.execute(count_query)
            stats["total_checked"] = result.scalar() or 0

            if stats["total_checked"] == 0:
                logger.info(
                    "unverified_account_cleanup_no_accounts",
                    message="No unverified accounts to delete",
                    cutoff_datetime=cutoff.isoformat(),
                )
            else:
                # Get emails for logging (before deletion)
                select_query = select(User.email).where(
                    User.is_verified.is_(False),
                    User.is_active.is_(False),
                    User.oauth_provider.is_(None),
                    User.created_at < cutoff,
                )
                result = await session.execute(select_query)
                emails = [row[0] for row in result.fetchall()]

                # Delete the accounts
                delete_query = delete(User).where(
                    User.is_verified.is_(False),
                    User.is_active.is_(False),
                    User.oauth_provider.is_(None),
                    User.created_at < cutoff,
                )
                delete_result = await session.execute(delete_query)
                await session.commit()

                stats["deleted"] = delete_result.rowcount  # type: ignore[attr-defined]
                # Log hashed emails for privacy
                stats["deleted_emails"] = [
                    f"{e[:3]}***@{e.split('@')[1] if '@' in e else '***'}"
                    for e in emails[:10]  # Max 10 for log readability
                ]

                logger.info(
                    "unverified_accounts_deleted",
                    count=stats["deleted"],
                    cutoff_datetime=cutoff.isoformat(),
                    sample_emails=stats["deleted_emails"],
                )

            break  # Exit after first session

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
