"""
Repository for the Psyche domain.

Provides data access methods for PsycheState and PsycheHistory models.
Follows the project convention: flush (not commit), structured logging,
async session, and type-safe queries.

Phase: evolution — Psyche Engine (Iteration 1)
Created: 2026-04-01
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.psyche.models import PsycheHistory, PsycheState
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class PsycheStateRepository:
    """Data access layer for PsycheState and PsycheHistory.

    Note: Does not inherit BaseRepository[T] because this repository manages
    TWO models (PsycheState + PsycheHistory) with a 1:1 relationship pattern
    that doesn't fit the single-model CRUD generic. Same pattern as
    JournalEntryRepository which also uses standalone class for similar reasons.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            db: SQLAlchemy async session (caller manages commit/rollback).
        """
        self.db = db

    # =========================================================================
    # PsycheState CRUD
    # =========================================================================

    async def get_by_user_id(self, user_id: UUID) -> PsycheState | None:
        """Get psyche state for a user.

        Args:
            user_id: User UUID.

        Returns:
            PsycheState or None if not found.
        """
        result = await self.db.execute(select(PsycheState).where(PsycheState.user_id == user_id))
        return result.scalar_one_or_none()

    async def create(self, state: PsycheState) -> PsycheState:
        """Create a new psyche state record.

        Args:
            state: PsycheState instance to persist.

        Returns:
            Created PsycheState with generated ID.
        """
        self.db.add(state)
        await self.db.flush()
        logger.info(
            "psyche_state_created",
            user_id=str(state.user_id),
            state_id=str(state.id),
        )
        return state

    async def update(self, state: PsycheState) -> PsycheState:
        """Flush pending changes on an already-tracked psyche state.

        No locking of any kind is performed: this is a plain flush of the
        session-tracked instance. The pre-response path (own session, commits
        the decayed state) and the fire-and-forget post-response task (own
        session, commits the appraisal) can race on the same row; the last
        commit wins whole-row. Acceptable today because both writers touch
        the same user sequentially in practice — revisit with SELECT ... FOR
        UPDATE if a real concurrent-writer path appears.

        Args:
            state: PsycheState instance with modified fields.

        Returns:
            Updated PsycheState.
        """
        await self.db.flush()
        return state

    async def delete_for_user(self, user_id: UUID) -> int:
        """Delete all psyche data for a user (GDPR compliance).

        Deletes both PsycheHistory and PsycheState records.

        Args:
            user_id: User UUID.

        Returns:
            Total number of deleted records.
        """
        # Delete history first (no FK constraint to psyche_states, but logically correct)
        history_result = await self.db.execute(
            delete(PsycheHistory).where(PsycheHistory.user_id == user_id)
        )
        history_count: int = getattr(history_result, "rowcount", 0) or 0

        state_result = await self.db.execute(
            delete(PsycheState).where(PsycheState.user_id == user_id)
        )
        state_count: int = getattr(state_result, "rowcount", 0) or 0

        total = history_count + state_count
        await self.db.flush()

        logger.info(
            "psyche_data_deleted",
            user_id=str(user_id),
            history_deleted=history_count,
            state_deleted=state_count,
            total_deleted=total,
        )
        return total

    # =========================================================================
    # PsycheHistory
    # =========================================================================

    async def create_snapshot(self, snapshot: PsycheHistory) -> PsycheHistory:
        """Create a psyche history snapshot.

        Args:
            snapshot: PsycheHistory instance to persist.

        Returns:
            Created PsycheHistory with generated ID.
        """
        self.db.add(snapshot)
        await self.db.flush()
        logger.debug(
            "psyche_snapshot_created",
            user_id=str(snapshot.user_id),
            snapshot_type=snapshot.snapshot_type,
        )
        return snapshot

    async def get_history(
        self,
        user_id: UUID,
        limit: int = 100,
        snapshot_type: str | None = None,
        hours: int | None = None,
    ) -> list[PsycheHistory]:
        """Get psyche history snapshots for a user.

        Args:
            user_id: User UUID.
            limit: Maximum number of snapshots to return.
            snapshot_type: Optional filter by snapshot type.
            hours: Optional filter to last N hours.

        Returns:
            List of PsycheHistory, ordered by created_at descending.
        """
        query = (
            select(PsycheHistory)
            .where(PsycheHistory.user_id == user_id)
            .order_by(PsycheHistory.created_at.desc())
            .limit(limit)
        )
        if snapshot_type:
            query = query.where(PsycheHistory.snapshot_type == snapshot_type)
        if hours:
            cutoff = datetime.now(UTC) - timedelta(hours=hours)
            query = query.where(PsycheHistory.created_at >= cutoff)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def delete_snapshots_older_than(
        self,
        user_id: UUID,
        days: int,
        now: datetime | None = None,
    ) -> int:
        """Delete a user's history snapshots older than a rolling time window.

        Rolling retention (N-201): keeps ``psyche_history`` bounded. Enforced on
        write, per user, right after a new snapshot is created. Uses the
        ``ix_psyche_history_user_created`` composite index.

        Args:
            user_id: User UUID whose old snapshots to purge.
            days: Retention window in days. Values ``<= 0`` disable retention
                (no query is issued, keep forever).
            now: Reference time (defaults to current UTC). Injectable for tests.

        Returns:
            Number of snapshots deleted.
        """
        if days <= 0:
            return 0

        cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
        result = await self.db.execute(
            delete(PsycheHistory).where(
                PsycheHistory.user_id == user_id,
                PsycheHistory.created_at < cutoff,
            )
        )
        deleted: int = getattr(result, "rowcount", 0) or 0
        await self.db.flush()

        if deleted:
            logger.info(
                "psyche_history_retention_purged",
                user_id=str(user_id),
                retention_days=days,
                deleted=deleted,
            )
        return deleted
