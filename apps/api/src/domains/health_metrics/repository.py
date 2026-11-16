"""Repositories for the Health Metrics domain.

Two repositories, both inheriting :class:`BaseRepository` for standard
CRUD / pagination / DB error classification / Prometheus instrumentation
(mirrors ``ConnectorRepository``, ``AttachmentRepository``, etc.):

- :class:`HealthSampleRepository` — polymorphic sample ingestion and
  window queries (bulk UPSERT, range fetches, bulk deletes).
- :class:`HealthMetricTokenRepository` — per-user ingestion token
  lifecycle (create, list, authenticate-by-hash, touch, revoke).

The batch upsert relies on PostgreSQL's ``INSERT ... ON CONFLICT ... DO
UPDATE ... RETURNING (xmax = 0)`` trick to discriminate new rows from
updated rows in a single round-trip (``xmax = 0`` means "no prior version"
== insert, otherwise update).

Project convention: flush (never commit), structured logging, async
session, type-safe queries.

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
Revised: 2026-04-21 — polymorphic samples + batch upsert.
Revised: 2026-04-22 — split into two ``BaseRepository`` subclasses (v1.17.2).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Date, cast, delete, func, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.health_metrics.baseline import DailyStat
from src.domains.health_metrics.fusion import counted_samples
from src.domains.health_metrics.management_lock import lock_health_writer
from src.domains.health_metrics.management_read import (
    health_sample_statement,
    health_token_statement,
)
from src.domains.health_metrics.models import HealthMetricToken, HealthSample
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CountedAggregate:
    """A window's counted values (:func:`~.fusion.counted_samples`), never empty.

    Attributes:
        rows: Counted rows: the samples of a ``KEEP_ALL`` kind, the fused
            slices of a ``MAX_RATE`` one (always >= 1).
        total: Sum of the counted values.
        minimum: Smallest counted value.
        maximum: Largest counted value.
    """

    rows: int
    total: float
    minimum: float
    maximum: float


@dataclass(frozen=True, slots=True)
class WindowSummary:
    """What one kind holds over a window (:meth:`HealthSampleRepository.fetch_window_summary`).

    Attributes:
        counted: The counted aggregate, None when nothing counts in the window.
        samples: Stored samples starting in the window, as received.
        last_start: Start of the latest stored sample, None without one.
        last_value: Value of the latest stored sample, None without one.
    """

    counted: CountedAggregate | None
    samples: int
    last_start: datetime | None
    last_value: int | None


# =============================================================================
# HealthSample repository
# =============================================================================


class HealthSampleRepository(BaseRepository[HealthSample]):
    """Data access layer for :class:`HealthSample`.

    Extends :class:`BaseRepository` for common CRUD / pagination and
    automatic Prometheus instrumentation. Domain-specific methods below
    cover the batch ingestion pipeline (bulk UPSERT with ``ON CONFLICT
    DO UPDATE``) and the window queries consumed by the aggregator,
    baseline computation, and agent summaries.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with an async DB session.

        Args:
            db: SQLAlchemy async session (caller manages commit/rollback).
        """
        super().__init__(db, HealthSample)

    # =========================================================================
    # Batch upsert
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
        await lock_health_writer(self.db, user_id)

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
    # Window queries
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
        stmt = health_sample_statement(user_id, kind=kind, from_ts=from_ts, to_ts=to_ts)
        stmt = (
            stmt.order_by(HealthSample.date_start.desc(), HealthSample.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def fetch_window_summary(
        self,
        user_id: UUID,
        *,
        kind: str,
        from_ts: datetime,
        to_ts: datetime,
    ) -> WindowSummary:
        """What one kind holds over a window, counted through the fusion door.

        Two statements, both bounded by the window: the counted aggregate
        (fused for a ``MAX_RATE`` kind, :func:`~.fusion.counted_samples`) and
        the stored samples' count with the latest one, kept as facts about
        what was received.

        Args:
            user_id: Owner user UUID.
            kind: Kind discriminator (must be a registered kind).
            from_ts: Inclusive lower bound.
            to_ts: Exclusive upper bound.

        Returns:
            The window's :class:`WindowSummary`.
        """
        counted = counted_samples(user_id, kind, from_ts=from_ts, to_ts=to_ts)
        rows, total, minimum, maximum = (
            await self.db.execute(
                select(
                    func.count(),
                    func.sum(counted.c.value),
                    func.min(counted.c.value),
                    func.max(counted.c.value),
                )
            )
        ).one()
        latest = (
            await self.db.execute(
                select(
                    func.count().over(),
                    HealthSample.date_start,
                    HealthSample.value,
                )
                .where(
                    HealthSample.user_id == user_id,
                    HealthSample.kind == kind,
                    HealthSample.date_start >= from_ts,
                    HealthSample.date_start < to_ts,
                )
                .order_by(HealthSample.date_start.desc(), HealthSample.id.desc())
                .limit(1)
            )
        ).first()
        return WindowSummary(
            counted=(
                CountedAggregate(
                    rows=int(rows),
                    total=float(total),
                    minimum=float(minimum),
                    maximum=float(maximum),
                )
                if rows
                else None
            ),
            samples=int(latest[0]) if latest is not None else 0,
            last_start=latest[1] if latest is not None else None,
            last_value=int(latest[2]) if latest is not None else None,
        )

    async def fetch_daily_stats(
        self,
        user_id: UUID,
        *,
        kind: str,
        zone: ZoneInfo,
        from_ts: datetime,
        to_ts: datetime,
    ) -> list[DailyStat]:
        """Return per-LOCAL-day aggregate primitives over a window, day ascending.

        Server-side rollup: one row per day instead of one row per sample.
        The baseline / variations / heartbeat paths only ever consume per-day
        aggregates, and shipping every raw sample to Python was a synchronous
        decode burst that froze the event loop for hundreds of milliseconds
        (~12 000 rows for a 36-day heart-rate window). PostgreSQL aggregates
        the same window in milliseconds and returns ~36 rows.

        Days are the person's: cut at their midnight through an explicit
        ``timezone(<zone>, ...)``, so the result never depends on the session
        ``TimeZone`` (ADR-148 amendment 2026-11-14 — a UTC day ran from 01:00
        to 01:00 in Paris in winter). Values are counted through the fusion
        door, so two devices measuring one walk count it once.

        Args:
            user_id: Owner user UUID.
            kind: Kind discriminator (must be a registered kind).
            zone: The person's zone, where days are cut.
            from_ts: Inclusive lower bound (a row belongs to the window of its start).
            to_ts: Exclusive upper bound.

        Returns:
            One :class:`DailyStat` per local day holding at least one counted
            row, ordered by day ascending.
        """
        counted = counted_samples(user_id, kind, from_ts=from_ts, to_ts=to_ts)
        day = cast(func.timezone(zone.key, counted.c.date_start), Date).label("day")
        stmt = (
            select(
                day,
                func.round(func.sum(counted.c.value)),
                func.count(),
                func.round(func.min(counted.c.value)),
            )
            .group_by(day)
            .order_by(day)
        )
        result = await self.db.execute(stmt)
        return [
            DailyStat(day=row[0], total=int(row[1]), count=int(row[2]), minimum=int(row[3]))
            for row in result.all()
        ]

    # =========================================================================
    # Bulk deletes (per-kind / per-user)
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


# =============================================================================
# HealthMetricToken repository
# =============================================================================


class HealthMetricTokenRepository(BaseRepository[HealthMetricToken]):
    """Data access layer for :class:`HealthMetricToken`.

    Extends :class:`BaseRepository` for standard CRUD and automatic
    Prometheus instrumentation. Domain-specific methods below cover the
    token authentication lifecycle (create a pre-hashed record,
    authenticate by hash, touch ``last_used_at``, revoke scoped by owner).
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with an async DB session.

        Args:
            db: SQLAlchemy async session (caller manages commit/rollback).
        """
        super().__init__(db, HealthMetricToken)

    async def create_token(self, token: HealthMetricToken) -> HealthMetricToken:
        """Persist a new ingestion token record.

        Unlike :meth:`BaseRepository.create` which takes a dict of field
        values, this method accepts a fully-constructed
        :class:`HealthMetricToken` because the caller (service layer)
        generates the raw value, SHA-256 hash, and display prefix in a
        single flow before handing over the ORM instance.

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
        stmt = health_token_statement(user_id).order_by(
            HealthMetricToken.created_at.desc(), HealthMetricToken.id.desc()
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_active_token_by_hash(self, token_hash: str) -> HealthMetricToken | None:
        """Return a non-revoked token of an ACTIVE owner matching the hash.

        Defense in depth (audit N-207.2): a token is only usable while its
        owner's account is active and not deleted — otherwise a deactivated
        or deleted user's device could keep ingesting samples even if some
        lifecycle flow forgot to revoke or purge the token row.

        Args:
            token_hash: SHA-256 hex digest of the raw token value.

        Returns:
            Active HealthMetricToken of an active, non-deleted owner, or None.
        """
        from src.domains.users.models import User

        stmt = (
            select(HealthMetricToken)
            .join(User, HealthMetricToken.user_id == User.id)
            .where(
                HealthMetricToken.token_hash == token_hash,
                HealthMetricToken.revoked_at.is_(None),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
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

    The merge strategy is read from the central kind registry (see
    :mod:`src.domains.health_metrics.kinds`). Current strategies:

    - :attr:`MergeStrategy.MAX` → keep the largest value (steps: Watch and
      iPhone count complementary subsets of movement).
    - :attr:`MergeStrategy.AVG_ROUNDED` → arithmetic mean rounded to int
      (heart_rate: sensor fusion of two devices targeting the same signal).
    - :attr:`MergeStrategy.MIN` / :attr:`MergeStrategy.SUM` / :attr:`MergeStrategy.LAST_WINS`
      supported for future kinds.

    Unknown kinds (not registered) fall back to last-wins for defensive
    forward-compat — application-level validation already rejects unknown
    kinds upstream.

    Args:
        samples: Post-validation normalized samples, in arrival order.
        kind: Sample discriminator driving the merge strategy.

    Returns:
        A list of samples with at most one entry per ``(date_start,
        date_end)`` tuple, preserving first-seen insertion order.
    """
    from src.domains.health_metrics.kinds import HEALTH_KINDS, MergeStrategy

    strategy = (
        HEALTH_KINDS[kind].merge_strategy if kind in HEALTH_KINDS else MergeStrategy.LAST_WINS
    )

    groups: dict[tuple[datetime, datetime], list[dict[str, Any]]] = {}
    for s in samples:
        groups.setdefault((s["date_start"], s["date_end"]), []).append(s)

    merged: list[dict[str, Any]] = []
    for group in groups.values():
        if len(group) == 1:
            merged.append(group[0])
            continue
        match strategy:
            case MergeStrategy.MAX:
                merged.append(max(group, key=lambda s: int(s["value"])))
            case MergeStrategy.MIN:
                merged.append(min(group, key=lambda s: int(s["value"])))
            case MergeStrategy.AVG_ROUNDED:
                avg_value = round(sum(int(s["value"]) for s in group) / len(group))
                representative = dict(group[-1])
                representative["value"] = avg_value
                merged.append(representative)
            case MergeStrategy.SUM:
                total = sum(int(s["value"]) for s in group)
                representative = dict(group[-1])
                representative["value"] = total
                merged.append(representative)
            case MergeStrategy.LAST_WINS:
                merged.append(group[-1])
    return merged
