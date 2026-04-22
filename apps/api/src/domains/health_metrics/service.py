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

import asyncio
import hashlib
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    HEALTH_METRICS_AGENT_CONTEXT_MAX_CHARS,
    HEALTH_METRICS_AGENT_SUMMARY_WINDOW_DAYS,
    HEALTH_METRICS_HEARTBEAT_FRESHNESS_MINUTES,
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
from src.domains.health_metrics.baseline import (
    baseline_window_start,
    compute_baseline,
)
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
from src.domains.health_metrics.kinds import (
    HEALTH_KINDS,
    AggregationMethod,
    HealthKindSpec,
    get_active_bounds,
    get_spec,
)
from src.domains.health_metrics.models import HealthMetricToken, HealthSample
from src.domains.health_metrics.repository import (
    HealthMetricTokenRepository,
    HealthSampleRepository,
)
from src.domains.health_metrics.schemas import (
    HealthIngestRejectedItem,
    HealthIngestResponse,
    HealthMetricAggregateResponse,
    HealthMetricTokenCreateResponse,
)
from src.domains.health_metrics.signals import (
    detect_notable_events,
    detect_recent_variations,
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

    Consumes the central :data:`HEALTH_KINDS` registry for all kind-specific
    semantics (payload key, bounds). Adding a new kind requires no change
    to this function — only a new entry in ``kinds.py``.

    Args:
        raw: Raw sample dict (parsed from the request body).
        kind: One of the keys of :data:`HEALTH_KINDS`.

    Returns:
        A :class:`_SampleValidation` — on success the ``payload`` dict
        holds the normalized columns ready for UPSERT; on failure, only
        the ``reason`` is populated.
    """
    try:
        spec = get_spec(kind)
    except KeyError:
        return _SampleValidation(
            valid=False,
            payload=None,
            reason=f"{REJECTION_REASON_MALFORMED}:unknown_kind",
        )

    try:
        date_start_raw = raw["date_start"]
        date_end_raw = raw["date_end"]
        value_raw = raw[spec.payload_value_key]
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

    lo, hi = get_active_bounds(spec)
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

        Instantiates two repositories (one per model) — mirrors the
        ``BaseRepository`` convention used by every other domain:
        :class:`HealthSampleRepository` for polymorphic sample
        ingestion and window queries, :class:`HealthMetricTokenRepository`
        for ingestion-token lifecycle.

        Args:
            db: SQLAlchemy async session (caller manages commit/rollback).
        """
        self.db = db
        self.sample_repo = HealthSampleRepository(db)
        self.token_repo = HealthMetricTokenRepository(db)

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

        inserted, updated, duplicates = await self.sample_repo.upsert_samples(
            token_record.user_id, kind, valid_payloads
        )
        now = datetime.now(UTC)
        await self.token_repo.touch_token_last_used(token_record.id, now)

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

        samples = await self.sample_repo.fetch_samples_asc(
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
        count = await self.sample_repo.delete_all_samples_for_user(user_id)
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
        count = await self.sample_repo.delete_samples_by_kind(user_id, kind)
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
        await self.token_repo.create_token(record)

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
        return await self.token_repo.list_tokens_for_user(user_id)

    async def revoke_token(self, user_id: UUID, token_id: UUID) -> bool:
        """Revoke one of the user's tokens.

        Args:
            user_id: Owner user UUID (ownership guard).
            token_id: Token record ID.

        Returns:
            True if the token was revoked, False if already revoked or missing.
        """
        ok = await self.token_repo.revoke_token(token_id, user_id, datetime.now(UTC))
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
        return await self.token_repo.get_active_token_by_hash(token_hash)

    # =========================================================================
    # Agent-facing read helpers (assistant agents v1.17.2)
    # =========================================================================

    async def compute_kind_summary(
        self,
        user_id: UUID,
        kind: str,
        *,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
    ) -> dict[str, Any]:
        """Summarize samples of a kind for an ISO 8601 time window.

        Mirrors the calendar-tools pattern (``time_min`` / ``time_max``):
        the planner receives the pre-resolved temporal range from the
        QueryAnalyzer's ``resolved_references`` (e.g. "this week" ->
        "2026-04-20 to 2026-04-26") and splits it across the two params.

        When both bounds are omitted the window defaults to "since
        midnight UTC of the current day" — what the user means by "today".

        Args:
            user_id: Owner user UUID.
            kind: Registered kind discriminator.
            time_min: Inclusive window start (UTC-aware). Defaults to
                today's midnight UTC when omitted.
            time_max: Exclusive window end (UTC-aware). Defaults to
                ``datetime.now(UTC)`` when omitted.

        Returns:
            A dict with keys ``kind``, ``unit``, ``from_ts``, ``to_ts``,
            ``total`` (or ``avg``/``min``/``max`` for AVG kinds),
            ``samples_count``, ``last_sample_at``, ``last_value``.
            When no samples are found, ``samples_count`` is 0 and the
            aggregate fields are ``None``.
        """
        spec = get_spec(kind)
        now = datetime.now(UTC)
        resolved_to = time_max or now
        resolved_from = time_min or now.replace(hour=0, minute=0, second=0, microsecond=0)
        samples = await self.sample_repo.fetch_samples_kind(
            user_id, kind=kind, from_ts=resolved_from, to_ts=resolved_to
        )

        last_sample_at: datetime | None = samples[-1].date_start if samples else None
        last_value: int | None = int(samples[-1].value) if samples else None

        result: dict[str, Any] = {
            "kind": spec.kind,
            "unit": spec.unit,
            "from_ts": resolved_from.isoformat(),
            "to_ts": resolved_to.isoformat(),
            "samples_count": len(samples),
            "last_sample_at": last_sample_at.isoformat() if last_sample_at else None,
            "last_value": last_value,
        }

        if not samples:
            return {**result, "total": None, "avg": None, "min": None, "max": None}

        values = [int(s.value) for s in samples]
        match spec.aggregation_method:
            case AggregationMethod.SUM:
                result["total"] = sum(values)
            case AggregationMethod.AVG_MIN_MAX:
                result["avg"] = round(sum(values) / len(values), 1)
                result["min"] = min(values)
                result["max"] = max(values)
            case AggregationMethod.LAST_VALUE:
                result["last"] = values[-1]
        return result

    async def compute_kind_daily_breakdown(
        self,
        user_id: UUID,
        kind: str,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        """Per-day aggregated values for a kind over the last ``days`` days.

        Args:
            user_id: Owner user UUID.
            kind: Registered kind discriminator.
            days: Window length; defaults to 7.

        Returns:
            A list of ``{"date": "YYYY-MM-DD", "value": float}`` dicts, one
            per day that has at least one sample, sorted ascending.
            Missing days are not emitted (let the LLM phrase the gap).
        """
        spec = get_spec(kind)
        now = datetime.now(UTC)
        resolved_from = (now - timedelta(days=days)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        samples = await self.sample_repo.fetch_samples_kind(
            user_id, kind=kind, from_ts=resolved_from, to_ts=now
        )

        from src.domains.health_metrics.baseline import _daily_aggregate, _group_samples_by_day

        by_day = _group_samples_by_day(samples)
        sorted_days = sorted(by_day.keys())
        values = _daily_aggregate(samples, spec.baseline_kind)
        return [
            {"date": day.isoformat(), "value": round(val, 1)}
            for day, val in zip(sorted_days, values, strict=True)
        ]

    async def compute_kind_baseline_delta(
        self,
        user_id: UUID,
        kind: str,
        window_days: int = HEALTH_METRICS_AGENT_SUMMARY_WINDOW_DAYS,
    ) -> dict[str, Any]:
        """Compare the last ``window_days`` to the user's baseline for a kind.

        Returns a dict with the baseline mode (``empty``/``bootstrap``/
        ``rolling``), the median baseline value, the per-window aggregate,
        and the percent delta.

        Args:
            user_id: Owner user UUID.
            kind: Registered kind discriminator.
            window_days: Recent window length; defaults to 7.

        Returns:
            A dict shaped for LLM consumption. When no data exists, returns
            ``{"kind": ..., "mode": "empty", ...}`` with nulls.
        """
        spec = get_spec(kind)
        now = datetime.now(UTC)
        # Fetch a window wide enough to split into:
        #   - last ``window_days`` (the "recent" slice compared against baseline)
        #   - the full rolling baseline window (28 days by default) before that
        # so the rolling median sees the full 28-day span, not 28 - window_days.
        from_ts = baseline_window_start(now) - timedelta(days=window_days)
        samples = await self.sample_repo.fetch_samples_kind(
            user_id, kind=kind, from_ts=from_ts, to_ts=now
        )

        from src.domains.health_metrics.baseline import _daily_aggregate, _group_samples_by_day

        by_day = _group_samples_by_day(samples)
        sorted_days = sorted(by_day.keys())
        if not sorted_days:
            return {
                "kind": spec.kind,
                "unit": spec.unit,
                "mode": "empty",
                "baseline_value": None,
                "window_value": None,
                "delta_pct": None,
                "window_days": window_days,
            }

        window_cutoff = sorted_days[-min(window_days, len(sorted_days))]
        baseline_samples = [
            s for s in samples if s.date_start.astimezone(UTC).date() < window_cutoff
        ]
        window_samples = [
            s for s in samples if s.date_start.astimezone(UTC).date() >= window_cutoff
        ]

        baseline = compute_baseline(baseline_samples, spec)
        window_vals = _daily_aggregate(window_samples, spec.baseline_kind)
        window_value = sum(window_vals) / len(window_vals) if window_vals else None

        delta_pct: float | None = None
        if baseline.median_value and window_value is not None and baseline.median_value != 0:
            delta_pct = round(
                (window_value - baseline.median_value) / baseline.median_value * 100.0, 1
            )

        return {
            "kind": spec.kind,
            "unit": spec.unit,
            "mode": baseline.mode,
            "baseline_value": (
                round(baseline.median_value, 1) if baseline.median_value is not None else None
            ),
            "window_value": round(window_value, 1) if window_value is not None else None,
            "delta_pct": delta_pct,
            "window_days": window_days,
            "days_available": baseline.days_available,
        }

    async def compute_overview(
        self,
        user_id: UUID,
        *,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Cross-kind summary for the ``get_health_overview`` tool.

        Iterates :data:`HEALTH_KINDS` so adding a new kind is transparent.
        Delegates to :meth:`compute_kind_summary` per kind — the same
        ``time_min`` / ``time_max`` semantics apply.

        Args:
            user_id: Owner user UUID.
            time_min: Inclusive window start (UTC-aware). Defaults to
                today's midnight UTC when omitted.
            time_max: Exclusive window end (UTC-aware). Defaults to
                ``datetime.now(UTC)`` when omitted.

        Returns:
            A dict keyed by kind, each value being the ``compute_kind_summary``
            result for that kind.
        """
        specs = list(HEALTH_KINDS.values())
        summaries = await asyncio.gather(
            *(
                self.compute_kind_summary(user_id, spec.kind, time_min=time_min, time_max=time_max)
                for spec in specs
            )
        )
        return {spec.kind: summary for spec, summary in zip(specs, summaries, strict=True)}

    async def detect_all_variations(
        self,
        user_id: UUID,
        window_days: int = HEALTH_METRICS_AGENT_SUMMARY_WINDOW_DAYS,
    ) -> list[dict[str, Any]]:
        """Detect notable recent variations across every registered kind.

        Combines :func:`detect_recent_variations` (directional streaks) with
        :func:`detect_notable_events` (structural events like inactivity).

        Args:
            user_id: Owner user UUID.
            window_days: Recent window length; defaults to 7.

        Returns:
            A list of event dicts (may be empty). Each dict has at least a
            ``kind`` key and an ``event`` or ``trend`` label.
        """
        now = datetime.now(UTC)
        # Extend the fetch by ``window_days`` so the baseline split inside
        # ``detect_recent_variations`` sees the full 28-day rolling history
        # *plus* the recent window on top of it (see ``compute_kind_baseline_delta``).
        from_ts = baseline_window_start(now) - timedelta(days=window_days)

        variations: list[dict[str, Any]] = []
        for spec in HEALTH_KINDS.values():
            samples = await self.sample_repo.fetch_samples_kind(
                user_id, kind=spec.kind, from_ts=from_ts, to_ts=now
            )
            if not samples:
                continue
            variation = detect_recent_variations(samples, spec, window_days=window_days)
            if variation is not None:
                variations.append(variation)
            for event in detect_notable_events(samples, spec, window_days=window_days):
                variations.append(event)
        return variations

    async def build_health_context_for_prompt(
        self,
        user_id: UUID,
        max_chars: int = HEALTH_METRICS_AGENT_CONTEXT_MAX_CHARS,
    ) -> str:
        """Build a short textual context block for prompt injection.

        Used by memory/journal/consolidation prompts when the user has
        opted into health-aware assistant integrations. Produces a compact
        string the LLM can reason about without exposing raw sensor values.

        Args:
            user_id: Owner user UUID.
            max_chars: Upper bound on the returned string length.

        Returns:
            A plain-text block (never None). Returns an empty string if no
            kind has data.
        """
        lines: list[str] = []
        variations = await self.detect_all_variations(user_id)
        for variation in variations:
            if "trend" in variation:
                lines.append(
                    f"- {variation['kind']}: {variation['trend']} "
                    f"over {variation.get('days', 0)} days "
                    f"(avg delta {variation.get('delta_pct', 0)}% vs baseline, "
                    f"mode={variation.get('baseline_mode', 'unknown')})"
                )
            elif "event" in variation:
                lines.append(
                    f"- {variation['kind']}: event={variation['event']} "
                    f"over {variation.get('days', 0)} days"
                )

        if not lines:
            return ""

        block = "Recent health signals (factual, not medical):\n" + "\n".join(lines)
        if len(block) > max_chars:
            block = block[: max_chars - 1] + "…"
        return block

    async def build_heartbeat_health_signals(
        self,
        user_id: UUID,
    ) -> dict[str, Any] | None:
        """Return the structured health-signals payload for the Heartbeat source.

        Combines:

        - ``summary_today`` — last-value + freshness per kind.
        - ``baseline_deltas`` — ``compute_kind_baseline_delta`` per kind.
        - ``recent_variations`` / ``notable_events`` from
          :meth:`detect_all_variations`.

        Args:
            user_id: Owner user UUID.

        Returns:
            A dict ready to attach to ``HeartbeatContext.health_signals``.
            Returns ``None`` if the user has zero samples across every kind
            (nothing meaningful to inject).
        """
        now = datetime.now(UTC)
        freshness_cutoff = now - timedelta(minutes=HEALTH_METRICS_HEARTBEAT_FRESHNESS_MINUTES)

        summary_today: dict[str, dict[str, Any]] = {}
        baseline_deltas: dict[str, dict[str, Any]] = {}
        any_data = False

        for spec in HEALTH_KINDS.values():
            samples_today = await self.sample_repo.fetch_samples_kind(
                user_id, kind=spec.kind, from_ts=freshness_cutoff, to_ts=now
            )
            if samples_today:
                any_data = True
                last_sample = samples_today[-1]
                minutes_ago = int((now - last_sample.date_start).total_seconds() / 60)
                summary_today[spec.kind] = {
                    "value": _summary_value(spec, samples_today),
                    "unit": spec.unit,
                    "last_update_minutes_ago": minutes_ago,
                }

            delta = await self.compute_kind_baseline_delta(user_id, spec.kind)
            if delta["mode"] != "empty":
                baseline_deltas[spec.kind] = {
                    "pct": delta["delta_pct"],
                    "mode": delta["mode"],
                    "baseline_value": delta["baseline_value"],
                }

        if not any_data and not baseline_deltas:
            return None

        variations_all = await self.detect_all_variations(user_id)
        recent_variations = [v for v in variations_all if "trend" in v]
        notable_events = [v for v in variations_all if "event" in v]

        return {
            "summary_today": summary_today,
            "baseline_deltas_7d": baseline_deltas,
            "recent_variations": recent_variations,
            "notable_events": notable_events,
        }


# =============================================================================
# Internal helpers
# =============================================================================


def _summary_value(spec: HealthKindSpec, samples: list[HealthSample]) -> int | float:
    """Single-scalar representation of today's samples for the Heartbeat card.

    - ``SUM`` aggregation → total across the window (e.g. steps).
    - ``AVG_MIN_MAX`` aggregation → rounded average (e.g. heart rate).
    - ``LAST_VALUE`` aggregation → last recorded value.

    Args:
        spec: Kind spec.
        samples: Non-empty list of samples.

    Returns:
        A scalar summarizing today's data for the kind.
    """
    values = [int(s.value) for s in samples]
    match spec.aggregation_method:
        case AggregationMethod.SUM:
            return sum(values)
        case AggregationMethod.AVG_MIN_MAX:
            return round(sum(values) / len(values), 1)
        case AggregationMethod.LAST_VALUE:
            return values[-1]


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
