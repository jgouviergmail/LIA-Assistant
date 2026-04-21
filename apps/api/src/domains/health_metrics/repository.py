"""Repository for the Health Metrics domain.

Data access methods for ``HealthSample`` and ``HealthMetricToken``.
Uses the project convention: ``flush`` (never commit), structured logging,
async session, and type-safe queries.

The batch upsert relies on PostgreSQL's ``INSERT ... ON CONFLICT ... DO
UPDATE ... RETURNING (xmax = 0)`` trick to discriminate new rows from
updated rows in a single round-trip (``xmax = 0`` means "no prior version"
== insert, otherwise update).

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
Revised: 2026-04-21 — polymorphic samples + batch upsert.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import HEALTH_METRICS_KIND_HEART_RATE, HEALTH_METRICS_KIND_STEPS
from src.domains.health_metrics.models import HealthMetricToken, HealthSample
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class HealthMetricsRepository:
    """Data access layer for health samples and ingestion tokens."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize repository with an async DB session.

        Args:
            db: SQLAlchemy async session (caller manages commit/rollback).
        """
        self.db = db

    # =========================================================================
    # HealthSample — batch upsert
    # =========================================================================

    async def upsert_samples(
        self,
        user_id: UUID,
        kind: str,
        samples: list[dict[str, Any]],
    ) -> tuple[int, int, int]:
        """Bulk UPSERT a batch of same-kind samples.

        Uses ``INSERT ... ON CONFLICT ... DO UPDATE`` on the unique constraint
        ``(user_id, kind, date_start, date_end)``. Uses the PostgreSQL-specific
        ``RETURNING (xmax = 0) AS inserted`` to count insert vs update in one
        round-trip.

        Args:
            user_id: Owner user UUID (applied to every row).
            kind: Sample kind discriminator (``"heart_rate"`` | ``"steps"``).
            samples: List of dicts with keys ``date_start``, ``date_end``,
                ``value``, ``source``. Caller is responsible for validation
                and date normalization.

        Returns:
            Tuple ``(inserted_count, updated_count, duplicates_collapsed)``.
            ``duplicates_collapsed`` counts intra-batch duplicates on
            ``(date_start, date_end)`` that were merged before the UPSERT.
            iOS Shortcuts can emit overlapping samples when the Apple Watch
            and iPhone both report the same interval; the merge strategy is
            per-kind — see :func:`_merge_duplicate_samples`.
        """
        if not samples:
            return (0, 0, 0)

        # Dedupe intra-batch on (date_start, date_end) before UPSERT.
        # PostgreSQL's ``ON CONFLICT ... DO UPDATE`` raises
        # ``CardinalityViolationError`` if the same target row is proposed
        # twice in a single statement. Arbitrage is per-kind:
        # - steps: MAX (Watch + iPhone count complementary subsets of
        #   movement; MAX approximates ground truth better than AVG or SUM).
        # - heart_rate: AVG (two sensors measuring the same physiological
        #   signal; averaging is the most honest fusion).
        deduped = _merge_duplicate_samples(samples, kind)
        duplicates_collapsed = len(samples) - len(deduped)

        now = datetime.now(UTC)
        rows = [
            {
                "id": uuid.uuid4(),
                "user_id": user_id,
                "kind": kind,
                "date_start": s["date_start"],
                "date_end": s["date_end"],
                "value": s["value"],
                "source": s["source"],
                "created_at": now,
                "updated_at": now,
            }
            for s in deduped
        ]
        stmt = pg_insert(HealthSample).values(rows)
        excluded = stmt.excluded
        upsert_stmt: Any = stmt.on_conflict_do_update(
            constraint="uq_health_samples_user_kind_range",
            set_={
                "value": excluded.value,
                "source": excluded.source,
                "updated_at": func.now(),
            },
        ).returning(literal_column("(xmax = 0)").label("inserted"))

        result = await self.db.execute(upsert_stmt)
        flags = [row.inserted for row in result.fetchall()]
        inserted = sum(1 for flag in flags if flag)
        updated = len(flags) - inserted
        await self.db.flush()
        return inserted, updated, duplicates_collapsed

    # =========================================================================
    # HealthSample — read
    # =========================================================================

    async def list_samples(
        self,
        user_id: UUID,
        *,
        kind: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[HealthSample]:
        """Return samples for a user, most recent first.

        Args:
            user_id: Owner user UUID.
            kind: Optional filter on discriminator.
            from_ts: Inclusive lower bound on ``date_start``.
            to_ts: Exclusive upper bound on ``date_start``.
            limit: Max rows to return.
            offset: Pagination offset.

        Returns:
            List of HealthSample ordered by ``date_start`` descending.
        """
        stmt = select(HealthSample).where(HealthSample.user_id == user_id)
        if kind is not None:
            stmt = stmt.where(HealthSample.kind == kind)
        if from_ts is not None:
            stmt = stmt.where(HealthSample.date_start >= from_ts)
        if to_ts is not None:
            stmt = stmt.where(HealthSample.date_start < to_ts)
        stmt = stmt.order_by(HealthSample.date_start.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def fetch_samples_asc(
        self,
        user_id: UUID,
        *,
        from_ts: datetime,
        to_ts: datetime,
    ) -> list[HealthSample]:
        """Return samples in ascending order over a window (for aggregation).

        Args:
            user_id: Owner user UUID.
            from_ts: Inclusive lower bound on ``date_start``.
            to_ts: Exclusive upper bound on ``date_start``.

        Returns:
            List of HealthSample ordered by ``date_start`` ascending.
        """
        stmt = (
            select(HealthSample)
            .where(
                HealthSample.user_id == user_id,
                HealthSample.date_start >= from_ts,
                HealthSample.date_start < to_ts,
            )
            .order_by(HealthSample.date_start.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # =========================================================================
    # HealthSample — delete
    # =========================================================================

    async def delete_samples_by_kind(self, user_id: UUID, kind: str) -> int:
        """Delete every sample of a given kind for a user.

        Args:
            user_id: Owner user UUID.
            kind: Sample kind discriminator.

        Returns:
            Number of rows deleted.
        """
        stmt = delete(HealthSample).where(
            HealthSample.user_id == user_id,
            HealthSample.kind == kind,
        )
        result = await self.db.execute(stmt)
        count: int = getattr(result, "rowcount", 0) or 0
        await self.db.flush()
        return count

    async def delete_all_samples_for_user(self, user_id: UUID) -> int:
        """Delete every sample (all kinds) for a user.

        Args:
            user_id: Owner user UUID.

        Returns:
            Number of rows deleted.
        """
        stmt = delete(HealthSample).where(HealthSample.user_id == user_id)
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

    async def get_active_token_by_hash(self, token_hash: str) -> HealthMetricToken | None:
        """Return a non-revoked token matching the hash, or None.

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
        """Update the ``last_used_at`` field after a successful ingestion.

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
        """Mark a token as revoked (scoped to its owner).

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


# =============================================================================
# Intra-batch dedupe / merge helpers
# =============================================================================


def _merge_duplicate_samples(
    samples: list[dict[str, Any]],
    kind: str,
) -> list[dict[str, Any]]:
    """Collapse samples sharing the same ``(date_start, date_end)`` tuple.

    Merge strategy is chosen per kind:

    - ``"steps"`` → MAX of ``value`` across the duplicate group. The Apple
      Watch and iPhone count complementary subsets of movement (worn on the
      wrist vs. carried in a pocket); neither is a superset of the other,
      so MAX approximates ground truth better than SUM (double-count) or
      AVG (under-count).

    - ``"heart_rate"`` → AVG (arithmetic mean, rounded to the nearest int)
      across the duplicate group. Both sensors aim at the same
      physiological signal; averaging is the most honest fusion.

    - Any other kind → last-wins (defensive forward-compat fallback;
      application-level validation already rejects unknown kinds upstream).

    Args:
        samples: Post-validation normalized samples, in arrival order.
        kind: Sample discriminator driving the merge strategy.

    Returns:
        A list of samples with at most one entry per ``(date_start,
        date_end)`` tuple, preserving first-seen insertion order.
    """
    groups: dict[tuple[datetime, datetime], list[dict[str, Any]]] = {}
    for s in samples:
        groups.setdefault((s["date_start"], s["date_end"]), []).append(s)

    merged: list[dict[str, Any]] = []
    for group in groups.values():
        if len(group) == 1:
            merged.append(group[0])
            continue
        if kind == HEALTH_METRICS_KIND_STEPS:
            winner = max(group, key=lambda s: int(s["value"]))
            merged.append(winner)
        elif kind == HEALTH_METRICS_KIND_HEART_RATE:
            avg_value = round(sum(int(s["value"]) for s in group) / len(group))
            representative = dict(group[-1])
            representative["value"] = avg_value
            merged.append(representative)
        else:
            merged.append(group[-1])
    return merged
