"""Repository for the Health Metrics domain.

Data access methods for HealthMetric and HealthMetricToken models. Uses the
project convention: `flush` (never commit), structured logging, async session,
and type-safe queries.

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.health_metrics.models import HealthMetric, HealthMetricToken
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class HealthMetricsRepository:
    """Data access layer for HealthMetric and HealthMetricToken.

    Does not inherit BaseRepository[T] because the repository manages two
    models with distinct semantics (samples vs tokens); same pattern as
    ``PsycheStateRepository``.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            db: SQLAlchemy async session (caller manages commit/rollback).
        """
        self.db = db

    # =========================================================================
    # HealthMetric CRUD
    # =========================================================================

    async def create_metric(self, metric: HealthMetric) -> HealthMetric:
        """Persist a new health metric sample.

        Args:
            metric: HealthMetric instance to persist.

        Returns:
            The persisted metric (with generated id).
        """
        self.db.add(metric)
        await self.db.flush()
        return metric

    async def list_metrics(
        self,
        user_id: UUID,
        *,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[HealthMetric]:
        """Return raw metrics for a user, most recent first.

        Args:
            user_id: Owner user UUID.
            from_ts: Inclusive lower bound on recorded_at.
            to_ts: Exclusive upper bound on recorded_at.
            limit: Max rows to return.
            offset: Pagination offset.

        Returns:
            List of HealthMetric rows ordered by recorded_at desc.
        """
        stmt = select(HealthMetric).where(HealthMetric.user_id == user_id)
        if from_ts is not None:
            stmt = stmt.where(HealthMetric.recorded_at >= from_ts)
        if to_ts is not None:
            stmt = stmt.where(HealthMetric.recorded_at < to_ts)
        stmt = stmt.order_by(HealthMetric.recorded_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def fetch_metrics_asc(
        self,
        user_id: UUID,
        *,
        from_ts: datetime,
        to_ts: datetime,
    ) -> list[HealthMetric]:
        """Return metrics in ascending order over a window (for aggregation).

        Ascending order keeps the aggregation deterministic for HR
        min/max within a bucket and lets the caller iterate samples
        in chronological order.

        Args:
            user_id: Owner user UUID.
            from_ts: Inclusive lower bound.
            to_ts: Exclusive upper bound.

        Returns:
            List of HealthMetric ordered by recorded_at asc.
        """
        stmt = (
            select(HealthMetric)
            .where(
                HealthMetric.user_id == user_id,
                HealthMetric.recorded_at >= from_ts,
                HealthMetric.recorded_at < to_ts,
            )
            .order_by(HealthMetric.recorded_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def nullify_field_for_user(self, user_id: UUID, field: str) -> int:
        """Set one column to NULL across all rows of a user.

        Used for the "delete all heart_rate" / "delete all steps" UI action.

        Args:
            user_id: Owner user UUID.
            field: Column name — must belong to the deletable allowlist.

        Returns:
            Number of rows updated.
        """
        # The caller (service layer) is responsible for validating `field`
        # against the deletable allowlist. This repository only executes SQL.
        stmt = update(HealthMetric).where(HealthMetric.user_id == user_id).values({field: None})
        result = await self.db.execute(stmt)
        count: int = getattr(result, "rowcount", 0) or 0
        await self.db.flush()
        return count

    async def delete_all_for_user(self, user_id: UUID) -> int:
        """Delete every HealthMetric row for a user.

        Args:
            user_id: Owner user UUID.

        Returns:
            Number of rows deleted.
        """
        stmt = delete(HealthMetric).where(HealthMetric.user_id == user_id)
        result = await self.db.execute(stmt)
        count: int = getattr(result, "rowcount", 0) or 0
        await self.db.flush()
        return count

    # =========================================================================
    # HealthMetricToken CRUD
    # =========================================================================

    async def create_token(self, token: HealthMetricToken) -> HealthMetricToken:
        """Persist a new ingestion token record.

        Args:
            token: HealthMetricToken instance (with hash + prefix already set).

        Returns:
            The persisted token (with generated id).
        """
        self.db.add(token)
        await self.db.flush()
        return token

    async def list_tokens_for_user(self, user_id: UUID) -> list[HealthMetricToken]:
        """Return every token owned by a user, most recent first.

        Args:
            user_id: Owner user UUID.

        Returns:
            List of HealthMetricToken ordered by created_at desc.
        """
        stmt = (
            select(HealthMetricToken)
            .where(HealthMetricToken.user_id == user_id)
            .order_by(HealthMetricToken.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_token_by_id(self, token_id: UUID, user_id: UUID) -> HealthMetricToken | None:
        """Return a specific token owned by a user.

        Args:
            token_id: Token record ID.
            user_id: Owner user UUID (ownership guard).

        Returns:
            HealthMetricToken or None if not found / not owned.
        """
        stmt = select(HealthMetricToken).where(
            HealthMetricToken.id == token_id,
            HealthMetricToken.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_token_by_hash(self, token_hash: str) -> HealthMetricToken | None:
        """Return a non-revoked token matching the hash, or None.

        Used by the ingestion endpoint to authenticate incoming requests.

        Args:
            token_hash: SHA-256 hex digest of the raw token value.

        Returns:
            Active HealthMetricToken or None.
        """
        stmt = select(HealthMetricToken).where(
            HealthMetricToken.token_hash == token_hash,
            HealthMetricToken.revoked_at.is_(None),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def touch_token_last_used(self, token_id: UUID, timestamp: datetime) -> None:
        """Update the `last_used_at` field after a successful ingestion.

        Args:
            token_id: Token record ID.
            timestamp: Usage timestamp (UTC).
        """
        stmt = (
            update(HealthMetricToken)
            .where(HealthMetricToken.id == token_id)
            .values(last_used_at=timestamp)
        )
        await self.db.execute(stmt)
        await self.db.flush()

    async def revoke_token(self, token_id: UUID, user_id: UUID, timestamp: datetime) -> bool:
        """Mark a token as revoked (owned by user).

        Args:
            token_id: Token record ID.
            user_id: Owner user UUID (ownership guard).
            timestamp: Revocation timestamp (UTC).

        Returns:
            True if the token was revoked, False if not found / already revoked.
        """
        stmt = (
            update(HealthMetricToken)
            .where(
                HealthMetricToken.id == token_id,
                HealthMetricToken.user_id == user_id,
                HealthMetricToken.revoked_at.is_(None),
            )
            .values(revoked_at=timestamp)
        )
        result = await self.db.execute(stmt)
        affected: int = getattr(result, "rowcount", 0) or 0
        await self.db.flush()
        return affected > 0
