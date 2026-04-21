"""Business logic for the Health Metrics domain.

Responsibilities:
- Token generation (cryptographically strong, SHA-256 hashed at rest),
  listing, revocation, and authentication.
- Ingestion pipeline with mixed per-field physiological validation
  (out-of-range values are nullified but neighboring valid fields are kept).
- Aggregation orchestration (delegates bucketing to ``aggregator.py``).
- Deletion (UPDATE field=NULL on scope='field', row DELETE on scope='all').

All failures are raised as centralized exceptions so the router layer stays
thin.

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
"""

from __future__ import annotations

import hashlib
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    HEALTH_METRICS_DELETABLE_FIELDS,
    HEALTH_METRICS_PERIOD_DAY,
    HEALTH_METRICS_PERIOD_HOUR,
    HEALTH_METRICS_PERIOD_MONTH,
    HEALTH_METRICS_PERIOD_WEEK,
    HEALTH_METRICS_PERIOD_YEAR,
    HEALTH_METRICS_SOURCE_DEFAULT,
    HEALTH_METRICS_SOURCE_MAX_LENGTH,
    HEALTH_METRICS_TOKEN_DISPLAY_PREFIX_CHARS,
    HEALTH_METRICS_TOKEN_HASH_ALGO,
    HEALTH_METRICS_TOKEN_PREFIX,
    HEALTH_METRICS_TOKEN_RANDOM_BYTES,
)
from src.core.exceptions import raise_invalid_input
from src.core.field_names import FIELD_HEART_RATE, FIELD_STEPS
from src.domains.health_metrics.aggregator import PeriodLiteral, aggregate_metrics
from src.domains.health_metrics.constants import (
    LOG_EVENT_METRIC_DELETED,
    LOG_EVENT_METRIC_FIELD_INVALID,
    LOG_EVENT_METRIC_INGESTED,
    LOG_EVENT_TOKEN_GENERATED,
    LOG_EVENT_TOKEN_REVOKED,
    REJECTION_REASON_OUT_OF_RANGE,
)
from src.domains.health_metrics.models import HealthMetric, HealthMetricToken
from src.domains.health_metrics.repository import HealthMetricsRepository
from src.domains.health_metrics.schemas import (
    HealthMetricAggregateResponse,
    HealthMetricIngestResponse,
    HealthMetricPayload,
    HealthMetricTokenCreateResponse,
)
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_health_metrics import (
    health_metrics_deleted_total,
    health_metrics_ingested_total,
    health_metrics_tokens_generated_total,
    health_metrics_tokens_revoked_total,
    health_metrics_validation_rejected_total,
)

logger = get_logger(__name__)


# =============================================================================
# Token value helpers
# =============================================================================


def _hash_token(raw_token: str) -> str:
    """Compute the SHA-256 hex digest of a raw token value.

    Args:
        raw_token: Raw token value (the ``hm_xxx`` string handed back to the
            user once at generation time).

    Returns:
        The 64-char SHA-256 hex digest used for DB storage and lookup.

    Raises:
        RuntimeError: If the configured hash algorithm constant ever drifts
            away from ``sha256`` (defense against silent auth weakening).
    """
    if HEALTH_METRICS_TOKEN_HASH_ALGO != "sha256":
        raise RuntimeError(f"Unsupported hash algo: {HEALTH_METRICS_TOKEN_HASH_ALGO}")
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _generate_raw_token() -> tuple[str, str]:
    """Generate a fresh raw token and compute its display prefix.

    Returns:
        Tuple (raw_token, display_prefix).
    """
    suffix = secrets.token_urlsafe(HEALTH_METRICS_TOKEN_RANDOM_BYTES)
    raw = f"{HEALTH_METRICS_TOKEN_PREFIX}{suffix}"
    prefix = raw[:HEALTH_METRICS_TOKEN_DISPLAY_PREFIX_CHARS]
    return raw, prefix


# =============================================================================
# Payload validation helpers
# =============================================================================


_VALID_SOURCE_CHARS: frozenset[str] = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_-")


def _normalize_source(raw: str | None) -> str:
    """Slugify the `o` field supplied by the client.

    The value is lowercased, stripped of accents, and reduced to the
    ``[a-z0-9_-]`` character set to guarantee a low-cardinality label
    suitable for Prometheus / DB indexing.
    """
    if raw is None:
        return HEALTH_METRICS_SOURCE_DEFAULT
    trimmed = raw.strip()
    if not trimmed:
        return HEALTH_METRICS_SOURCE_DEFAULT
    # Strip accents (NFKD decomposition then drop combining marks).
    decomposed = unicodedata.normalize("NFKD", trimmed)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    lowered = ascii_only.lower()
    filtered = "".join(c for c in lowered if c in _VALID_SOURCE_CHARS)
    if not filtered:
        return HEALTH_METRICS_SOURCE_DEFAULT
    return filtered[:HEALTH_METRICS_SOURCE_MAX_LENGTH]


@dataclass(slots=True)
class _FieldOutcome:
    """Result of validating one payload field."""

    stored_value: int | None
    was_stored: bool  # True if the payload carried a value that survived validation
    was_nullified: bool  # True if the payload carried a value that failed validation


def _validate_heart_rate(value: int | None) -> _FieldOutcome:
    """Validate a heart-rate sample using mixed per-field semantics.

    Out-of-range values are nullified (stored as NULL) so they do not pollute
    aggregations, but the surrounding fields of the same payload are kept.

    Args:
        value: Raw heart rate (bpm) or None if absent in the payload.

    Returns:
        A `_FieldOutcome` describing the persisted value and validation flags.

    Notes:
        Logs do NOT include the raw heart-rate value (RGPD: special-category
        health data must not be duplicated into observability storage). The
        out-of-range direction is reported instead via a low-cardinality flag.
    """
    if value is None:
        return _FieldOutcome(stored_value=None, was_stored=False, was_nullified=False)
    lo = settings.health_metrics_heart_rate_min
    hi = settings.health_metrics_heart_rate_max
    if value < lo or value > hi:
        logger.warning(
            LOG_EVENT_METRIC_FIELD_INVALID,
            field=FIELD_HEART_RATE,
            direction="below_min" if value < lo else "above_max",
            min=lo,
            max=hi,
            reason=REJECTION_REASON_OUT_OF_RANGE,
        )
        health_metrics_validation_rejected_total.labels(
            field=FIELD_HEART_RATE,
            reason=REJECTION_REASON_OUT_OF_RANGE,
        ).inc()
        return _FieldOutcome(stored_value=None, was_stored=False, was_nullified=True)
    return _FieldOutcome(stored_value=int(value), was_stored=True, was_nullified=False)


def _validate_steps(value: int | None) -> _FieldOutcome:
    """Validate a per-period steps sample using mixed per-field semantics.

    Args:
        value: Raw step count for the inter-sample period (NOT a daily
            cumulative), or None if absent.

    Returns:
        A `_FieldOutcome` describing the persisted value and validation flags.

    Notes:
        Same RGPD-aware logging policy as :func:`_validate_heart_rate`: the
        raw value is never logged.
    """
    if value is None:
        return _FieldOutcome(stored_value=None, was_stored=False, was_nullified=False)
    lo = settings.health_metrics_steps_min
    hi = settings.health_metrics_steps_max
    if value < lo or value > hi:
        logger.warning(
            LOG_EVENT_METRIC_FIELD_INVALID,
            field=FIELD_STEPS,
            direction="below_min" if value < lo else "above_max",
            min=lo,
            max=hi,
            reason=REJECTION_REASON_OUT_OF_RANGE,
        )
        health_metrics_validation_rejected_total.labels(
            field=FIELD_STEPS,
            reason=REJECTION_REASON_OUT_OF_RANGE,
        ).inc()
        return _FieldOutcome(stored_value=None, was_stored=False, was_nullified=True)
    return _FieldOutcome(stored_value=int(value), was_stored=True, was_nullified=False)


# =============================================================================
# Service class
# =============================================================================


class HealthMetricsService:
    """Business operations for the Health Metrics domain."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize service with database session.

        Args:
            db: SQLAlchemy async session (caller manages commit/rollback).
        """
        self.db = db
        self.repo = HealthMetricsRepository(db)

    # =========================================================================
    # Ingestion
    # =========================================================================

    async def ingest(
        self,
        *,
        token_record: HealthMetricToken,
        payload: HealthMetricPayload,
    ) -> HealthMetricIngestResponse:
        """Persist one ingestion payload under the authenticated user.

        Implements mixed-per-field validation: invalid fields are stored as
        NULL, valid neighboring fields of the same payload are preserved.

        Args:
            token_record: Authenticated, non-revoked token.
            payload: Validated HealthMetricPayload (short-keyed DTO).

        Returns:
            HealthMetricIngestResponse describing which fields were stored.
        """
        now = datetime.now(UTC)

        hr_outcome = _validate_heart_rate(payload.c)
        steps_outcome = _validate_steps(payload.p)
        source = _normalize_source(payload.o)

        metric = HealthMetric(
            user_id=token_record.user_id,
            recorded_at=now,
            heart_rate=hr_outcome.stored_value,
            steps=steps_outcome.stored_value,
            source=source,
        )
        await self.repo.create_metric(metric)
        await self.repo.touch_token_last_used(token_record.id, now)

        stored_fields: list[str] = []
        nullified_fields: list[str] = []
        if hr_outcome.was_stored:
            stored_fields.append(FIELD_HEART_RATE)
        if hr_outcome.was_nullified:
            nullified_fields.append(FIELD_HEART_RATE)
        if steps_outcome.was_stored:
            stored_fields.append(FIELD_STEPS)
        if steps_outcome.was_nullified:
            nullified_fields.append(FIELD_STEPS)

        status: Literal["accepted", "partial"] = "partial" if nullified_fields else "accepted"

        logger.info(
            LOG_EVENT_METRIC_INGESTED,
            user_id=str(token_record.user_id),
            token_id=str(token_record.id),
            source=source,
            status=status,
            stored_fields=stored_fields,
            nullified_fields=nullified_fields,
        )
        health_metrics_ingested_total.labels(status=status).inc()

        return HealthMetricIngestResponse(
            status=status,
            recorded_at=now,
            stored_fields=stored_fields,
            nullified_fields=nullified_fields,
        )

    # =========================================================================
    # Aggregation
    # =========================================================================

    async def aggregate(
        self,
        *,
        user_id: UUID,
        period: Literal["hour", "day", "week", "month", "year"],
        from_ts: datetime | None,
        to_ts: datetime | None,
    ) -> HealthMetricAggregateResponse:
        """Compute bucketed aggregates for visualization.

        If ``from_ts`` / ``to_ts`` are omitted, defaults are picked to match
        the semantic of each period (e.g. last 24h for `hour`, last 7 days
        for `day`, last 12 months for `month`).

        Args:
            user_id: Owner user UUID.
            period: Requested bucket size.
            from_ts: Inclusive window start (UTC); defaulted if None.
            to_ts: Exclusive window end (UTC); defaulted if None.

        Returns:
            HealthMetricAggregateResponse.
        """
        resolved_to = to_ts or datetime.now(UTC)
        resolved_from = from_ts or (resolved_to - _default_window_for(period))

        metrics = await self.repo.fetch_metrics_asc(
            user_id,
            from_ts=resolved_from,
            to_ts=resolved_to,
        )
        points, averages = aggregate_metrics(
            metrics,
            period=period,
            from_ts=resolved_from,
            to_ts=resolved_to,
        )
        return HealthMetricAggregateResponse(
            period=period,
            from_ts=resolved_from,
            to_ts=resolved_to,
            points=points,
            averages=averages,
        )

    # =========================================================================
    # Deletion
    # =========================================================================

    async def delete_all(self, user_id: UUID) -> int:
        """Delete every metric row for a user.

        Args:
            user_id: Owner user UUID.

        Returns:
            Number of deleted rows.
        """
        count = await self.repo.delete_all_for_user(user_id)
        logger.info(
            LOG_EVENT_METRIC_DELETED,
            user_id=str(user_id),
            scope="all",
            affected_rows=count,
        )
        health_metrics_deleted_total.labels(scope="all").inc()
        return count

    async def delete_field(self, user_id: UUID, field: str) -> int:
        """Nullify one metric column across every row of a user.

        Args:
            user_id: Owner user UUID.
            field: Column name. Must be in the deletable allowlist.

        Returns:
            Number of rows updated.
        """
        if field not in HEALTH_METRICS_DELETABLE_FIELDS:
            raise_invalid_input(
                f"Unsupported deletion field: {field}",
                allowed=list(HEALTH_METRICS_DELETABLE_FIELDS),
            )
        count = await self.repo.nullify_field_for_user(user_id, field)
        logger.info(
            LOG_EVENT_METRIC_DELETED,
            user_id=str(user_id),
            scope="field",
            field=field,
            affected_rows=count,
        )
        health_metrics_deleted_total.labels(scope="field").inc()
        return count

    # =========================================================================
    # Token management
    # =========================================================================

    async def create_token(
        self, user_id: UUID, label: str | None = None
    ) -> HealthMetricTokenCreateResponse:
        """Issue a new ingestion token for a user.

        Args:
            user_id: Owner user UUID.
            label: Optional user-supplied label.

        Returns:
            The token record enriched with the raw value (returned ONCE).
        """
        raw, prefix = _generate_raw_token()
        record = HealthMetricToken(
            user_id=user_id,
            token_hash=_hash_token(raw),
            token_prefix=prefix,
            label=label,
        )
        await self.repo.create_token(record)

        logger.info(
            LOG_EVENT_TOKEN_GENERATED,
            user_id=str(user_id),
            token_id=str(record.id),
            prefix=prefix,
        )
        health_metrics_tokens_generated_total.inc()

        return HealthMetricTokenCreateResponse(
            id=record.id,
            token=raw,
            token_prefix=prefix,
            label=record.label,
            created_at=record.created_at,
        )

    async def list_tokens(self, user_id: UUID) -> list[HealthMetricToken]:
        """Return every token owned by a user, most recent first.

        Args:
            user_id: Owner user UUID.

        Returns:
            All ingestion tokens for the user, including revoked ones (the UI
            renders a revoked badge so the user can see past identifiers).
        """
        return await self.repo.list_tokens_for_user(user_id)

    async def revoke_token(self, user_id: UUID, token_id: UUID) -> bool:
        """Revoke one of the user's tokens.

        Args:
            user_id: Owner user UUID (ownership guard).
            token_id: Token record ID.

        Returns:
            True if the token was revoked, False if already revoked / missing.
        """
        ok = await self.repo.revoke_token(token_id, user_id, datetime.now(UTC))
        if ok:
            logger.info(
                LOG_EVENT_TOKEN_REVOKED,
                user_id=str(user_id),
                token_id=str(token_id),
            )
            health_metrics_tokens_revoked_total.inc()
        return ok

    async def authenticate_token(self, raw_token: str) -> HealthMetricToken | None:
        """Resolve a raw token value to its active DB record.

        Args:
            raw_token: Raw token supplied via Authorization header.

        Returns:
            HealthMetricToken if the hash matches a non-revoked record, else None.
        """
        if not raw_token:
            return None
        token_hash = _hash_token(raw_token)
        return await self.repo.get_active_token_by_hash(token_hash)


# =============================================================================
# Default windows
# =============================================================================


def _default_window_for(period: PeriodLiteral) -> timedelta:
    """Return the default lookback window for each period granularity.

    Args:
        period: One of the supported period literals.

    Returns:
        A timedelta sized so the chart shows enough buckets without
        overwhelming the response (24 buckets for hour, 7 for day, …).
        Falls back to a 7-day window for unknown values rather than raising,
        so the endpoint stays robust to a future literal addition.
    """
    if period == HEALTH_METRICS_PERIOD_HOUR:
        return timedelta(hours=24)
    if period == HEALTH_METRICS_PERIOD_DAY:
        return timedelta(days=7)
    if period == HEALTH_METRICS_PERIOD_WEEK:
        return timedelta(days=7 * 12)
    if period == HEALTH_METRICS_PERIOD_MONTH:
        return timedelta(days=365)
    if period == HEALTH_METRICS_PERIOD_YEAR:
        return timedelta(days=365 * 5)
    return timedelta(days=7)
