"""Bounded removal of expired unverified signups through the full account lifecycle."""

import time
from datetime import UTC, datetime, timedelta
from typing import TypedDict
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.core.constants import (
    CONVERSATION_OWNER_LOCK_SCOPE,
    SCHEDULER_JOB_UNVERIFIED_CLEANUP,
    UNVERIFIED_ACCOUNT_CLEANUP_BATCH_SIZE,
    UNVERIFIED_ACCOUNT_CLEANUP_DAYS,
)
from src.domains.users.account_deletion_service import AccountDeletionService
from src.domains.users.account_erasure import erase_purged_account
from src.domains.users.models import User
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database.owner_lock import hold_owner_lock
from src.infrastructure.database.session import get_db_context
from src.infrastructure.locks import SchedulerLock
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)

logger = structlog.get_logger(__name__)


class CleanupReport(TypedDict, total=False):
    """Exact outcomes; an incomplete account remains available to the next sweep."""

    total_checked: int
    deleted: int
    failed: int
    cutoff_datetime: str
    status: str
    reason: str


def _eligible(cutoff: datetime) -> ColumnElement[bool]:
    """Selection and locked recheck share the complete signup policy."""
    return (
        User.is_verified.is_(False)
        & User.is_active.is_(False)
        & User.is_superuser.is_(False)
        & User.oauth_provider.is_(None)
        & (User.created_at < cutoff)
    )


async def purge_unverified_account(db: AsyncSession, owner: UUID, cutoff: datetime) -> bool:
    """Revalidate before irreversible cleanup; never infer absence of personal data."""
    await hold_owner_lock(db, CONVERSATION_OWNER_LOCK_SCOPE, owner)
    user = await db.scalar(
        select(User)
        .where(User.id == owner, _eligible(cutoff))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None:
        await db.commit()
        return False
    if not user.is_deleted:
        await AccountDeletionService(db).delete_account(owner, None, reason="unverified_signup")
    await erase_purged_account(db, owner)
    await db.commit()
    return True


async def _sweep() -> CleanupReport:
    """Do no network work on the selection session and isolate each account's failure."""
    cutoff = datetime.now(UTC) - timedelta(days=UNVERIFIED_ACCOUNT_CLEANUP_DAYS)
    async with get_db_context() as db:
        total = await db.scalar(select(func.count(User.id)).where(_eligible(cutoff))) or 0
        identities = list(
            await db.scalars(
                select(User.id)
                .where(_eligible(cutoff))
                .order_by(User.created_at, User.id)
                .limit(UNVERIFIED_ACCOUNT_CLEANUP_BATCH_SIZE)
            )
        )
    deleted, failed = 0, 0
    for owner in identities:
        try:
            async with get_db_context() as db:
                deleted += int(await purge_unverified_account(db, owner, cutoff))
        except Exception as exc:
            failed += 1
            background_job_errors_total.labels(job_name=SCHEDULER_JOB_UNVERIFIED_CLEANUP).inc()
            logger.warning(
                "unverified_account_cleanup_deferred",
                user_id=str(owner),
                error_type=type(exc).__name__,
            )
    logger.info(
        "unverified_accounts_deleted",
        count=deleted,
        failed=failed,
        total_checked=total,
        cutoff_datetime=cutoff.isoformat(),
    )
    return CleanupReport(
        total_checked=total, deleted=deleted, failed=failed, cutoff_datetime=cutoff.isoformat()
    )


async def cleanup_unverified_accounts() -> CleanupReport:
    """Retain the distributed scheduler lock for the entire bounded sweep."""
    start = time.perf_counter()
    try:
        redis = await get_redis_cache()
        if redis is None:
            return await _sweep()
        async with SchedulerLock(redis, SCHEDULER_JOB_UNVERIFIED_CLEANUP) as lock:
            if not lock.acquired:
                return CleanupReport(status="skipped", reason="lock_busy")
            return await _sweep()
    except Exception as exc:
        background_job_errors_total.labels(job_name=SCHEDULER_JOB_UNVERIFIED_CLEANUP).inc()
        logger.error("unverified_account_cleanup_failed", error_type=type(exc).__name__)
        raise
    finally:
        background_job_duration_seconds.labels(job_name=SCHEDULER_JOB_UNVERIFIED_CLEANUP).observe(
            time.perf_counter() - start
        )
