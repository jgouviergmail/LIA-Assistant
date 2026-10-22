"""Independent elected tick, bounded fair batches and durable per-owner claims."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_PROACTIVE_DISCUSSIONS
from src.domains.proactive_discussions.context_store.maintenance import expire_context
from src.domains.proactive_discussions.context_store.models import ContextStateRecord
from src.domains.proactive_discussions.finance_repository import SpendRepository
from src.domains.proactive_discussions.models import DiscussionPreference, DiscussionRun
from src.domains.proactive_discussions.policy import may_start
from src.domains.proactive_discussions.policy_repository import policy_value
from src.domains.users.models import User
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database.session import get_db_context
from src.infrastructure.locks.scheduler_lock import SchedulerLock, ttl_for_interval
from src.infrastructure.proactive.discussion_delivery import dispatch_pending_discussions
from src.infrastructure.proactive.discussion_run_setup import configured_limits
from src.infrastructure.proactive.discussion_runner import run_for_owner

logger = structlog.get_logger(__name__)


async def process_proactive_discussions() -> dict[str, int]:
    """Run one elected producer tick.

    Context retention runs first, whatever the producer's state; then, only while
    the producer is on and its spending limits are set, pending deliveries go out,
    abandoned reservations are settled, and a small fair batch of owners is served,
    a requested rebuild first.

    Returns:
        How many owners were served, completed and failed.
    """
    redis = await get_redis_cache()
    async with SchedulerLock(
        redis,
        SCHEDULER_JOB_PROACTIVE_DISCUSSIONS,
        ttl_seconds=ttl_for_interval(settings.discussion_interval_minutes * 60),
    ) as lock:
        if not lock.acquired:
            return {"processed": 0}
        await maintain_discussion_context()
        if not settings.proactive_discussions_enabled or configured_limits() is None:
            return {"processed": 0}
        await dispatch_pending_discussions()
        now = datetime.now(UTC)
        async with get_db_context() as db:
            await SpendRepository(db).recover_expired(
                now=now, limit=settings.discussion_maintenance_batch_size
            )
            owners = await select_owners(db, now=now)
        semaphore = asyncio.Semaphore(settings.discussion_tick_concurrency)

        async def process(owner: UUID) -> str:
            async with semaphore:
                async with get_db_context() as db:
                    epoch = await db.scalar(
                        select(DiscussionPreference.context_epoch)
                        .join(
                            ContextStateRecord,
                            ContextStateRecord.user_id == DiscussionPreference.user_id,
                        )
                        .where(
                            DiscussionPreference.user_id == owner,
                            ContextStateRecord.refresh_requested.is_(True),
                        )
                    )
                return await run_for_owner(owner, rebuild_epoch=epoch)

        outcomes = await asyncio.gather(
            *(process(owner) for owner in owners), return_exceptions=True
        )
        _log_owner_faults(owners, outcomes)
        await dispatch_pending_discussions()
        return {
            "processed": len(outcomes),
            "completed": sum(value == "completed" for value in outcomes),
            "failed": sum(
                isinstance(value, BaseException) or value == "failed" for value in outcomes
            ),
        }


async def select_owners(db: AsyncSession, *, now: datetime) -> tuple[UUID, ...]:
    """The owners this tick can actually serve, a requested rebuild first.

    A rebuild ignores the discussion hours (the person asked for it); any other
    run needs its window open and no pause, by the policy's own predicate. The
    daily cap stays the claim's to check. An owner outside its hours no longer
    takes one of the batch's places, nor has its controls read for nothing.

    Args:
        db: A read session.
        now: The tick's clock.

    Returns:
        At most ``discussion_tick_owners`` owners, drawn at random among the
        ``discussion_tick_candidates`` examined.
    """
    recent = select(DiscussionRun.id).where(
        DiscussionRun.user_id == User.id,
        (DiscussionRun.claimed_at > now - timedelta(minutes=settings.discussion_interval_minutes))
        | (
            (DiscussionRun.retry_after > now)
            & (DiscussionRun.policy_revision == DiscussionPreference.revision)
            & (DiscussionRun.context_epoch == DiscussionPreference.context_epoch)
        ),
    )
    rows = (
        await db.execute(
            select(DiscussionPreference, User, ContextStateRecord.refresh_requested)
            .join(User, User.id == DiscussionPreference.user_id)
            .outerjoin(ContextStateRecord, ContextStateRecord.user_id == User.id)
            .options(load_only(User.id, User.timezone))
            .where(
                User.is_active.is_(True),
                User.is_verified.is_(True),
                User.deleted_at.is_(None),
                DiscussionPreference.enabled.is_(True),
                ~recent.exists(),
            )
            .order_by(func.random())
            .limit(settings.discussion_tick_candidates)
        )
    ).all()
    rebuilds = [user.id for _, user, requested in rows if requested]
    openings = [
        user.id
        for preference, user, requested in rows
        if not requested and may_start(policy_value(preference, user), now=now, openings_today=0)
    ]
    return tuple((rebuilds + openings)[: settings.discussion_tick_owners])


def _log_owner_faults(owners: tuple[UUID, ...], outcomes: list[str | BaseException]) -> None:
    """One owner's fault never stops the batch, and never goes unseen."""
    for owner, outcome in zip(owners, outcomes, strict=True):
        if isinstance(outcome, BaseException):
            logger.warning(
                "discussion_owner_run_failed",
                user_id=str(owner),
                error_type=type(outcome).__name__,
            )


async def maintain_discussion_context() -> None:
    """Expire the context past its retention for the least recently maintained accounts.

    At most ``discussion_maintenance_batch_size`` per tick; one account's failure is
    logged and retried at the next tick, the others are still served.
    """
    async with get_db_context() as db:
        maintenance_owners = tuple(
            (
                await db.scalars(
                    select(ContextStateRecord.user_id)
                    .join(User, User.id == ContextStateRecord.user_id)
                    .where(User.is_active.is_(True), User.deleted_at.is_(None))
                    .order_by(ContextStateRecord.updated_at, ContextStateRecord.user_id)
                    .limit(settings.discussion_maintenance_batch_size)
                )
            ).all()
        )
    for owner in maintenance_owners:
        try:
            async with get_db_context() as db:
                await expire_context(db, owner, now=datetime.now(UTC))
                state = await db.scalar(
                    select(ContextStateRecord).where(ContextStateRecord.user_id == owner)
                )
                if state is not None:
                    state.updated_at = datetime.now(UTC)
        except Exception as exc:
            # Retention must reach every other owner; this one is retried next tick.
            logger.warning(
                "discussion_context_maintenance_failed",
                user_id=str(owner),
                error_type=type(exc).__name__,
            )
