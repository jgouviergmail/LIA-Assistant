"""Business logic for the Health Metrics domain.

Responsibilities:

- **Token management**: cryptographically strong generation, SHA-256 hash
  storage, issuance, listing, revocation, and Authorization-header
  resolution.
- **Batch ingestion**: per-kind validation (physiological bounds, ISO 8601
  date parsing, UTC normalization, source slugification) and idempotent
  upsert into ``health_samples`` via the repository's bulk upsert.
- **Aggregation**: delegates bucketing to ``aggregator.aggregate_samples``
  after fetching the window of samples from the DB.
- **Deletion**: per-kind (DELETE WHERE kind=?) or full (DELETE all).

The service layer raises centralized exceptions so the router stays thin.

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
Revised: 2026-04-21 — polymorphic samples + batch upsert pipeline.
"""

from __future__ import annotations

import hashlib
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    HEALTH_METRICS_KIND_HEART_RATE,
    HEALTH_METRICS_KINDS,
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
from src.domains.health_metrics.aggregator import PeriodLiteral, aggregate_samples
from src.domains.health_metrics.constants import (
    LOG_EVENT_BATCH_DUPLICATES_COLLAPSED,
    LOG_EVENT_SAMPLE_REJECTED,
    LOG_EVENT_SAMPLES_DELETED,
    LOG_EVENT_SAMPLES_INGESTED,
    LOG_EVENT_TOKEN_GENERATED,
    LOG_EVENT_TOKEN_REVOKED,
    REJECTION_REASON_INVALID_DATE,
    REJECTION_REASON_MALFORMED,
    REJECTION_REASON_MISSING_FIELD,
    REJECTION_REASON_OUT_OF_RANGE,
    UPSERT_OPERATION_INSERT,
    UPSERT_OPERATION_UPDATE,
)
from src.domains.health_metrics.models import HealthMetricToken
from src.domains.health_metrics.repository import HealthMetricsRepository
from src.domains.health_metrics.schemas import (
    HealthIngestRejectedItem,
    HealthIngestResponse,
    HealthMetricAggregateResponse,
    HealthMetricTokenCreateResponse,
)
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_health_metrics import (
    health_metrics_deleted_total,
    health_metrics_tokens_generated_total,
    health_metrics_tokens_revoked_total,
    health_metrics_validation_rejected_total,
    health_samples_batch_duplicates_total,
    health_samples_upserted_total,
)

logger = get_logger(__name__)


# =============================================================================
# Token value helpers
# =============================================================================


def _hash_token(raw_token: str) -> str:
    """Compute the SHA-256 hex digest of a raw token value.

    Args:
        raw_token: Raw token value (``hm_…`` string handed back to the user
            once at generation time).

    Returns:
        The 64-char SHA-256 hex digest used for DB storage and lookup.

    Raises:
        RuntimeError: If the configured hash algorithm ever drifts away from
            ``sha256`` (defensive guard against silent auth weakening).
    """
    if HEALTH_METRICS_TOKEN_HASH_ALGO != "sha256":
        raise RuntimeError(f"Unsupported hash algo: {HEALTH_METRICS_TOKEN_HASH_ALGO}")
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _generate_raw_token() -> tuple[str, str]:
    """Generate a fresh raw token and compute its display prefix.

    Returns:
        Tuple ``(raw_token, display_prefix)``.
    """
    suffix = secrets.token_urlsafe(HEALTH_METRICS_TOKEN_RANDOM_BYTES)
    raw = f"{HEALTH_METRICS_TOKEN_PREFIX}{suffix}"
    prefix = raw[:HEALTH_METRICS_TOKEN_DISPLAY_PREFIX_CHARS]
    return raw, prefix


# =============================================================================
# Payload normalization helpers
# =============================================================================


_VALID_SOURCE_CHARS: frozenset[str] = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_-")


def _normalize_source(raw: str | None) -> str:
    """Slugify the ``o`` (origin) field supplied by the client.

    Lowercases, strips accents (NFKD + drop combining marks), and reduces
    to the ``[a-z0-9_-]`` character set. Guarantees a low-cardinality label
    suitable for DB indexing and Prometheus reuse.

    Args:
        raw: Raw source label, or None/empty.

    Returns:
        A slugified, length-capped string. Returns
        :data:`HEALTH_METRICS_SOURCE_DEFAULT` if the input is empty or
        reduces to nothing after normalization.
    """
    if raw is None:
        return HEALTH_METRICS_SOURCE_DEFAULT
    trimmed = raw.strip()
    if not trimmed:
        return HEALTH_METRICS_SOURCE_DEFAULT
    decomposed = unicodedata.normalize("NFKD", trimmed)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    lowered = ascii_only.lower()
    filtered = "".join(c for c in lowered if c in _VALID_SOURCE_CHARS)
    if not filtered:
        return HEALTH_METRICS_SOURCE_DEFAULT
    return filtered[:HEALTH_METRICS_SOURCE_MAX_LENGTH]


def _normalize_datetime(raw: Any) -> datetime:
    """Normalize a raw datetime or ISO 8601 string to UTC, second-truncated.

    Accepts a string (any tz) or an existing tz-aware datetime. Rejects
    naive datetimes — the ingestion contract mandates timezone-aware
    timestamps so UPSERT uniqueness is stable across TZ offsets.

    Args:
        raw: String (ISO 8601) or aware ``datetime``.

    Returns:
        Timezone-aware ``datetime`` in UTC, truncated to the second.

    Raises:
        ValueError: If the input cannot be parsed or has no timezone info.
    """
    if isinstance(raw, datetime):
        value = raw
    elif isinstance(raw, str):
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    else:
        raise ValueError(f"Unsupported datetime type: {type(raw).__name__}")
    if value.tzinfo is None:
        raise ValueError("Timezone-naive datetime rejected; provide ISO 8601 with TZ offset")
    return value.astimezone(UTC).replace(microsecond=0)


@dataclass(slots=True)
class _SampleValidation:
    """Outcome of validating one raw sample from the batch."""

    valid: bool
    payload: dict[str, Any] | None
    reason: str | None


def _validate_sample(raw: dict[str, Any], kind: str) -> _SampleValidation:
    """Validate a single raw sample for a given kind.

    Args:
        raw: Raw sample dict (parsed from the request body).
        kind: One of ``HEALTH_METRICS_KINDS``.

    Returns:
        A :class:`_SampleValidation` — on success the ``payload`` dict
        holds the normalized columns ready for UPSERT; on failure, only
        the ``reason`` is populated.
    """
    value_key = "heart_rate" if kind == HEALTH_METRICS_KIND_HEART_RATE else "steps"
    try:
        date_start_raw = raw["date_start"]
        date_end_raw = raw["date_end"]
        value_raw = raw[value_key]
    except KeyError as exc:
        return _SampleValidation(
            valid=False,
            payload=None,
            reason=f"{REJECTION_REASON_MISSING_FIELD}:{exc.args[0]}",
        )

    try:
        date_start = _normalize_datetime(date_start_raw)
        date_end = _normalize_datetime(date_end_raw)
    except (ValueError, TypeError) as exc:
        return _SampleValidation(
            valid=False,
            payload=None,
            reason=f"{REJECTION_REASON_INVALID_DATE}:{exc}",
        )

    try:
        value = int(value_raw)
    except (ValueError, TypeError):
        return _SampleValidation(
            valid=False,
            payload=None,
            reason=f"{REJECTION_REASON_MALFORMED}:value",
        )

    if kind == HEALTH_METRICS_KIND_HEART_RATE:
        lo = settings.health_metrics_heart_rate_min
        hi = settings.health_metrics_heart_rate_max
    else:
        lo = settings.health_metrics_steps_min
        hi = settings.health_metrics_steps_max
    if value < lo or value > hi:
        return _SampleValidation(
            valid=False,
            payload=None,
            reason=f"{REJECTION_REASON_OUT_OF_RANGE}:{'below_min' if value < lo else 'above_max'}",
        )

    return _SampleValidation(
        valid=True,
        payload={
            "date_start": date_start,
            "date_end": date_end,
            "value": value,
            "source": _normalize_source(raw.get("o")),
        },
        reason=None,
    )


# =============================================================================
# Service class
# =============================================================================


class HealthMetricsService:
    """Business operations for the Health Metrics domain."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize service with a DB session.

        Args:
            db: SQLAlchemy async session (caller manages commit/rollback).
        """
        self.db = db
        self.repo = HealthMetricsRepository(db)

    # =========================================================================
    # Batch ingestion
    # =========================================================================

    async def ingest_batch(
        self,
        *,
        token_record: HealthMetricToken,
        kind: str,
        raw_samples: list[dict[str, Any]],
    ) -> HealthIngestResponse:
        """Validate and upsert a batch of same-kind samples.

        Args:
            token_record: Authenticated, non-revoked ingestion token
                (ownership guard: ``user_id`` is taken from here).
            kind: Discriminator for the batch (``"heart_rate"`` or
                ``"steps"``).
            raw_samples: Parsed samples from the request body (any of the
                accepted envelope shapes has already been flattened to a
                plain list of dicts by the router).

        Returns:
            :class:`HealthIngestResponse` with counts and per-sample
            rejection reasons.
        """
        if kind not in HEALTH_METRICS_KINDS:
            raise_invalid_input(
                f"Unsupported kind: {kind}",
                allowed=list(HEALTH_METRICS_KINDS),
            )

        valid_payloads: list[dict[str, Any]] = []
        rejected: list[HealthIngestRejectedItem] = []

        for idx, raw in enumerate(raw_samples):
            if not isinstance(raw, dict):
                rejected.append(
                    HealthIngestRejectedItem(
                        index=idx,
                        reason=f"{REJECTION_REASON_MALFORMED}:not_a_dict",
                    )
                )
                health_metrics_validation_rejected_total.labels(
                    field=kind, reason=REJECTION_REASON_MALFORMED
                ).inc()
                continue

            outcome = _validate_sample(raw, kind)
            if outcome.valid and outcome.payload is not None:
                valid_payloads.append(outcome.payload)
            else:
                reason = outcome.reason or REJECTION_REASON_MALFORMED
                rejected.append(HealthIngestRejectedItem(index=idx, reason=reason))
                # Prometheus label uses the reason prefix (low cardinality).
                label = reason.split(":", 1)[0]
                health_metrics_validation_rejected_total.labels(field=kind, reason=label).inc()
                logger.warning(
                    LOG_EVENT_SAMPLE_REJECTED,
                    user_id=str(token_record.user_id),
                    kind=kind,
                    index=idx,
                    reason=reason,
                )

        inserted, updated, duplicates = await self.repo.upsert_samples(
            token_record.user_id, kind, valid_payloads
        )
        now = datetime.now(UTC)
        await self.repo.touch_token_last_used(token_record.id, now)

        if inserted:
            health_samples_upserted_total.labels(kind=kind, operation=UPSERT_OPERATION_INSERT).inc(
                inserted
            )
        if updated:
            health_samples_upserted_total.labels(kind=kind, operation=UPSERT_OPERATION_UPDATE).inc(
                updated
            )
        if duplicates:
            health_samples_batch_duplicates_total.labels(kind=kind).inc(duplicates)
            logger.warning(
                LOG_EVENT_BATCH_DUPLICATES_COLLAPSED,
                user_id=str(token_record.user_id),
                kind=kind,
                duplicates=duplicates,
                received=len(raw_samples),
            )

        # Accounting contract for the response:
        #   received = inserted + updated + rejected
        # Intra-batch duplicates collapse with last-wins semantics, so we
        # fold them into ``updated`` (the value for that (date_start, date_end)
        # was overwritten — just by a sibling in the same batch instead of a
        # prior DB row).
        reported_updated = updated + duplicates

        logger.info(
            LOG_EVENT_SAMPLES_INGESTED,
            user_id=str(token_record.user_id),
            token_id=str(token_record.id),
            kind=kind,
            received=len(raw_samples),
            inserted=inserted,
            updated=reported_updated,
            duplicates=duplicates,
            rejected=len(rejected),
        )

        return HealthIngestResponse(
            received=len(raw_samples),
            inserted=inserted,
            updated=reported_updated,
            rejected=rejected,
        )

    # =========================================================================
    # Aggregation
    # =========================================================================

    async def aggregate(
        self,
        *,
        user_id: UUID,
        period: PeriodLiteral,
        from_ts: datetime | None,
        to_ts: datetime | None,
    ) -> HealthMetricAggregateResponse:
        """Compute bucketed aggregates for visualization.

        Args:
            user_id: Owner user UUID.
            period: Requested bucket size.
            from_ts: Inclusive window start (UTC); defaulted by period.
            to_ts: Exclusive window end (UTC); defaults to ``now()``.

        Returns:
            :class:`HealthMetricAggregateResponse` ready for the frontend.
        """
        resolved_to = to_ts or datetime.now(UTC)
        resolved_from = from_ts or (resolved_to - _default_window_for(period))

        samples = await self.repo.fetch_samples_asc(
            user_id, from_ts=resolved_from, to_ts=resolved_to
        )
        points, averages = aggregate_samples(
            samples,
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
        """Delete every sample for a user across all kinds.

        Args:
            user_id: Owner user UUID.

        Returns:
            Number of rows deleted.
        """
        count = await self.repo.delete_all_samples_for_user(user_id)
        logger.info(
            LOG_EVENT_SAMPLES_DELETED,
            user_id=str(user_id),
            scope="all",
            affected_rows=count,
        )
        health_metrics_deleted_total.labels(scope="all").inc()
        return count

    async def delete_by_kind(self, user_id: UUID, kind: str) -> int:
        """Delete every sample of a given kind for a user.

        Args:
            user_id: Owner user UUID.
            kind: Must be one of ``HEALTH_METRICS_KINDS``.

        Returns:
            Number of rows deleted.
        """
        if kind not in HEALTH_METRICS_KINDS:
            raise_invalid_input(
                f"Unsupported kind: {kind}",
                allowed=list(HEALTH_METRICS_KINDS),
            )
        count = await self.repo.delete_samples_by_kind(user_id, kind)
        logger.info(
            LOG_EVENT_SAMPLES_DELETED,
            user_id=str(user_id),
            scope="kind",
            kind=kind,
            affected_rows=count,
        )
        health_metrics_deleted_total.labels(scope="kind").inc()
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
            All ingestion tokens for the user, including revoked ones.
        """
        return await self.repo.list_tokens_for_user(user_id)

    async def revoke_token(self, user_id: UUID, token_id: UUID) -> bool:
        """Revoke one of the user's tokens.

        Args:
            user_id: Owner user UUID (ownership guard).
            token_id: Token record ID.

        Returns:
            True if the token was revoked, False if already revoked or missing.
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


def _default_window_for(period: Literal["hour", "day", "week", "month", "year"]) -> timedelta:
    """Return the default lookback window for each period granularity.

    Args:
        period: One of the supported period literals.

    Returns:
        A timedelta sized so the chart shows enough buckets without
        overwhelming the response.
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
