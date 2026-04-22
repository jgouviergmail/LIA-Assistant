"""Pydantic v2 schemas for the Health Metrics domain.

Covers:
- Batch ingestion (per-kind: steps or heart_rate) with mixed client payload
  shapes (iOS Shortcuts wrapping, NDJSON, JSON array, `{"data": [...]}`) —
  the parsing happens at the router layer; this module only types the
  *validated* sample after parsing.
- Raw sample listing and aggregated visualization.
- Deletion by kind or full wipe.
- Token management (list / create / revoke).

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
Revised: 2026-04-21 — polymorphic samples + batch upsert contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.constants import HEALTH_METRICS_SOURCE_MAX_LENGTH

# =============================================================================
# Ingestion — incoming sample types
# =============================================================================


class HealthStepsSampleIn(BaseModel):
    """One steps sample as received in a batch.

    The ``date_start`` / ``date_end`` fields accept any ISO 8601 string with
    timezone (e.g. ``"2026-04-21T14:30:00+02:00"``). Pydantic v2 parses these
    into tz-aware datetimes; the service layer then normalizes to UTC.
    """

    date_start: datetime = Field(description="Start of the measurement interval (ISO 8601).")
    date_end: datetime = Field(description="End of the measurement interval (ISO 8601).")
    steps: int = Field(description="Number of steps recorded in the interval.")
    o: str | None = Field(
        default=None,
        max_length=HEALTH_METRICS_SOURCE_MAX_LENGTH,
        description="Origin label for this specific sample (e.g. 'iphone').",
    )


class HealthHeartRateSampleIn(BaseModel):
    """One heart-rate sample as received in a batch."""

    date_start: datetime = Field(description="Start of the measurement interval (ISO 8601).")
    date_end: datetime = Field(description="End of the measurement interval (ISO 8601).")
    heart_rate: int = Field(description="Heart rate (bpm) recorded in the interval.")
    o: str | None = Field(
        default=None,
        max_length=HEALTH_METRICS_SOURCE_MAX_LENGTH,
        description="Origin label for this specific sample (e.g. 'iphone').",
    )


# =============================================================================
# Ingestion — response
# =============================================================================


class HealthIngestRejectedItem(BaseModel):
    """A single sample that was not persisted, with its index and reason."""

    index: int = Field(description="0-based index of the rejected sample in the batch.")
    reason: str = Field(description="Human-readable rejection reason.")


class HealthIngestResponse(BaseModel):
    """Response returned by the batch ingestion endpoints."""

    received: int = Field(description="Total samples parsed from the request.")
    inserted: int = Field(description="New samples written to the database.")
    updated: int = Field(description="Existing samples whose value was overwritten (upsert).")
    rejected: list[HealthIngestRejectedItem] = Field(
        default_factory=list,
        description="Samples that failed validation (out of range, malformed date, …).",
    )


# =============================================================================
# Raw sample rows (listing endpoint)
# =============================================================================


class HealthSampleRow(BaseModel):
    """Single persisted sample as returned by the listing endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Row UUID.")
    kind: Literal["heart_rate", "steps"] = Field(description="Sample kind.")
    date_start: datetime = Field(description="Start of the measurement interval (UTC).")
    date_end: datetime = Field(description="End of the measurement interval (UTC).")
    value: int = Field(description="Numeric value (bpm for HR, count for steps).")
    source: str = Field(description="Origin label.")


# =============================================================================
# Aggregation
# =============================================================================


class HealthMetricAggregatePoint(BaseModel):
    """One aggregated point on the chart.

    Heart-rate fields aggregate by average / min / max across the bucket's
    samples. ``steps_total`` is the simple sum of the per-sample step counts.

    The typed legacy fields (``heart_rate_*``, ``steps_total``) are kept for
    backward compatibility with the existing frontend charts. The polymorphic
    ``metrics_by_kind`` field exposes the same data keyed by kind so new
    kinds (sleep, SpO2, ...) can be added without schema extensions.
    """

    bucket: datetime = Field(description="Start of the bucket window (UTC).")
    heart_rate_avg: float | None = Field(
        default=None, description="Average heart rate in the bucket."
    )
    heart_rate_min: int | None = Field(default=None, description="Min heart rate in the bucket.")
    heart_rate_max: int | None = Field(default=None, description="Max heart rate in the bucket.")
    steps_total: int | None = Field(
        default=None,
        description="Total steps recorded during the bucket (sum of samples).",
    )
    metrics_by_kind: dict[str, dict[str, int | float]] | None = Field(
        default=None,
        description=(
            "Polymorphic per-kind metrics, mirroring the legacy fields and "
            "future-proof for additional kinds. Keys are kind discriminators; "
            "inner dicts carry method-specific values (e.g. ``avg``/``min``/"
            "``max`` for AVG_MIN_MAX aggregation, ``sum`` for SUM aggregation)."
        ),
    )
    has_data: bool = Field(description="False if the bucket contains no sample at all.")


class HealthMetricPeriodAverages(BaseModel):
    """Overall averages across the requested period."""

    heart_rate_avg: float | None = Field(description="Period-wide heart rate average.")
    steps_per_day_avg: float | None = Field(description="Period-wide daily-step average.")


class HealthMetricAggregateResponse(BaseModel):
    """Aggregation endpoint response."""

    period: Literal["hour", "day", "week", "month", "year"] = Field(description="Bucket size.")
    from_ts: datetime = Field(description="Inclusive window start (UTC).")
    to_ts: datetime = Field(description="Exclusive window end (UTC).")
    points: list[HealthMetricAggregatePoint] = Field(description="Aggregated bucketed data.")
    averages: HealthMetricPeriodAverages = Field(description="Period-wide averages.")


# =============================================================================
# Deletion
# =============================================================================


class HealthMetricDeleteResponse(BaseModel):
    """Response returned after a delete operation."""

    scope: Literal["all", "kind"] = Field(description="Deletion scope.")
    kind: Literal["heart_rate", "steps"] | None = Field(
        default=None,
        description="Sample kind (only for scope='kind').",
    )
    affected_rows: int = Field(description="Number of rows deleted.")


# =============================================================================
# Tokens
# =============================================================================


class HealthMetricTokenCreateRequest(BaseModel):
    """Request body for creating a new ingestion token."""

    label: str | None = Field(
        default=None,
        max_length=64,
        description="Optional user-supplied label.",
    )


class HealthMetricTokenCreateResponse(BaseModel):
    """Response returned when a new token is created.

    The raw token value is only ever exposed here — on subsequent listings,
    only the prefix is available.
    """

    id: UUID = Field(description="Token record ID.")
    token: str = Field(description="Raw token value (returned ONCE, store it securely).")
    token_prefix: str = Field(description="Display prefix (also persisted).")
    label: str | None = Field(description="Optional label.")
    created_at: datetime = Field(description="Creation timestamp.")


class HealthMetricTokenRow(BaseModel):
    """One token as returned in the listing (secret value is NOT returned)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Token record ID.")
    token_prefix: str = Field(description="Display prefix.")
    label: str | None = Field(description="Optional label.")
    created_at: datetime = Field(description="Creation timestamp.")
    last_used_at: datetime | None = Field(description="Last successful ingestion.")
    revoked_at: datetime | None = Field(description="Revocation timestamp, if any.")


class HealthMetricTokenListResponse(BaseModel):
    """Listing of tokens owned by the current user."""

    tokens: list[HealthMetricTokenRow] = Field(default_factory=list, description="Tokens.")
