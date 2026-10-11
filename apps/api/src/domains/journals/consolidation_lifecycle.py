"""Per-account lease and optimistic snapshot for short consolidation settlement."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.journals.consolidation_controls import check_consolidation_work
from src.domains.journals.source_state import portrait_source_state
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context


@dataclass(frozen=True)
class ConsolidationSnapshot:
    owner: UUID
    journal_revision: int
    consent_revision: int
    captured_at: datetime
    sources: dict[str, Any]


@dataclass
class ConsolidationAttempt:
    """Caller-local outcome; a refused claim must not reuse an older success."""

    status: str = "failed"


def _refuse(attempt: ConsolidationAttempt | None, status: str) -> None:
    if attempt is not None:
        attempt.status = status


async def _allowed(user: User | None, *, manual: bool) -> bool:
    return bool(
        user
        and user.is_active
        and user.deleted_at is None
        and user.journals_enabled
        and (manual or user.journal_consolidation_enabled)
        and settings.journals_enabled
        and await is_capability_enabled(PlatformCapability.JOURNALS)
    )


async def claim_consolidation(
    user_id: UUID, owner: UUID, *, manual: bool, attempt: ConsolidationAttempt | None = None
) -> ConsolidationSnapshot | None:
    """Only the lease holder may pay for this account's consolidation."""
    async with get_db_context() as db:
        user = await db.scalar(select(User).where(User.id == user_id).with_for_update())
        if not await _allowed(user, manual=manual):
            _refuse(attempt, "disabled")
            return None
        assert user is not None
        await check_consolidation_work(db)
        now = datetime.now(UTC)
        if user.journal_consolidation_held_until and user.journal_consolidation_held_until > now:
            _refuse(attempt, "busy")
            return None
        if not manual and user.journal_last_attempted_at is not None:
            cooldown = now - timedelta(hours=settings.journal_consolidation_cooldown_hours)
            if user.journal_last_attempted_at >= cooldown:
                _refuse(attempt, "busy")
                return None
        if not manual and not await consolidation_needed(db, user):
            _refuse(attempt, "no_op")
            return None
        source_state = await portrait_source_state(db, user)
        user.journal_consolidation_owner = owner
        user.journal_consolidation_held_until = now + timedelta(
            seconds=settings.journal_consolidation_timeout_seconds + 30
        )
        user.journal_last_attempted_at = now
        user.journal_last_attempt_status = "running"
        snapshot = ConsolidationSnapshot(
            owner, user.journal_revision, user.extraction_revision, now, source_state
        )
        await db.commit()
        return snapshot


async def current_snapshot(
    db: AsyncSession,
    user_id: UUID,
    snapshot: ConsolidationSnapshot,
    *,
    manual: bool,
    lock: bool = False,
) -> User | None:
    """Check consent, rule work and all source identities at the paid/write boundaries."""
    query = select(User).where(User.id == user_id).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update()
    user = await db.scalar(query)
    if not await _allowed(user, manual=manual):
        return None
    assert user is not None
    await check_consolidation_work(db)
    if (
        user.journal_consolidation_owner != snapshot.owner
        or user.journal_consolidation_held_until is None
        or user.journal_consolidation_held_until <= datetime.now(UTC)
        or user.journal_revision != snapshot.journal_revision
        or user.extraction_revision != snapshot.consent_revision
        or await portrait_source_state(db, user) != snapshot.sources
    ):
        return None
    return user


async def finish_attempt(user_id: UUID, snapshot: ConsolidationSnapshot, status: str) -> None:
    """A failed/invalid/stale attempt consumes pacing, never the successful watermark."""
    async with get_db_context() as db:
        await db.execute(
            update(User)
            .where(User.id == user_id, User.journal_consolidation_owner == snapshot.owner)
            .values(
                journal_last_attempt_status=status,
                journal_consolidation_owner=None,
                journal_consolidation_held_until=None,
            )
        )
        await db.commit()


async def consolidation_needed(db: AsyncSession, user: User) -> bool:
    """Filter candidates without model calls; deletion and gate changes count."""
    fresh = await db.scalar(
        select(User).where(User.id == user.id).execution_options(populate_existing=True)
    )
    if fresh is None:
        return False
    user = fresh
    if user.journal_last_attempt_status in (
        "sources_unavailable",
        "failed",
        "invalid_output",
        "stale",
    ):
        return True
    if user.journal_consolidated_revision != user.journal_revision:
        return True
    provenance = user.journal_portrait_sources
    if not isinstance(provenance, dict):
        return True
    if provenance.get("portrait_pending") is True:
        return True
    return provenance.get("source_state") != await portrait_source_state(db, user)
