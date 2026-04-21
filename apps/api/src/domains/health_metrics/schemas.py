"""Pydantic v2 schemas for the Health Metrics domain.

Defines request and response models for:
- Ingestion (external POST authenticated by token)
- Raw metric listing
- Aggregated visualizations (hour/day/week/month/year buckets)
- Deletion (by field or all)
- Token management (list, create, revoke)

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.constants import (
    HEALTH_METRICS_SOURCE_MAX_LENGTH,
)
from src.domains.health_metrics.constants import (
    INGEST_STATUS_ACCEPTED,
    INGEST_STATUS_PARTIAL,
)

# =============================================================================
# Ingestion
# =============================================================================


class HealthMetricPayload(BaseModel):
    """Inner payload sent by the iPhone Shortcut.

    Short keys are used on purpose: the Shortcut editor on iOS is much easier
    to maintain with terse parameter names.
    """

    c: int | None = Field(
        default=None,
        description="Last heart rate sample (bpm).",
    )
    p: int | None = Field(
        default=None,
        description="Steps recorded since the previous sample (NOT a daily cumulative).",
    )
    o: str | None = Field(
        default=None,
        max_length=HEALTH_METRICS_SOURCE_MAX_LENGTH,
        description="Origin label (e.g. 'iphone'). Slugified server-side.",
    )


class HealthMetricIngestRequest(BaseModel):
    """Root ingestion request body.

    Wrapped in a `data` object per product contract: keeps room for future
    envelope metadata without breaking the inner payload.
    """

    data: HealthMetricPayload = Field(description="Metric values supplied by the client.")


class HealthMetricIngestResponse(BaseModel):
    """Response returned to the ingestion client.

    Status is `accepted` if every provided field was stored as-is, or
    `partial` if at least one field was out of range and persisted as NULL.
    """

    status: Literal["accepted", "partial"] = Field(
        description="Ingestion outcome.",
        examples=[INGEST_STATUS_ACCEPTED, INGEST_STATUS_PARTIAL],
    )
    recorded_at: datetime = Field(description="Server-side reception timestamp (UTC).")
    stored_fields: list[str] = Field(
        default_factory=list,
        description="Names of fields that were successfully stored.",
    )
    nullified_fields: list[str] = Field(
        default_factory=list,
        description="Names of fields that were provided but stored as NULL (out of range).",
    )


# =============================================================================
# Raw metric rows
# =============================================================================


class HealthMetricRow(BaseModel):
    """Single health metric row as returned by the listing endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Metric row ID.")
    recorded_at: datetime = Field(description="Server-side reception timestamp (UTC).")
    heart_rate: int | None = Field(description="Heart rate (bpm) or None.")
    steps: int | None = Field(description="Steps over the inter-sample period, or None.")
    source: str = Field(description="Origin label.")


# =============================================================================
# Aggregation
# =============================================================================


class HealthMetricAggregatePoint(BaseModel):
    """One aggregated point on the chart.

    Heart-rate fields aggregate by average / min / max across the bucket's
    samples. ``steps_total`` is the simple sum of the per-sample step counts
    (each sample already represents the increment over its inter-sample
    period).
    """

    bucket: datetime = Field(description="Start of the bucket window (UTC).")
    heart_rate_avg: float | None = Field(description="Average heart rate in the bucket.")
    heart_rate_min: int | None = Field(description="Min heart rate in the bucket.")
    heart_rate_max: int | None = Field(description="Max heart rate in the bucket.")
    steps_total: int | None = Field(
        description=("Total steps recorded during the bucket " "(sum of per-sample increments)."),
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

    scope: Literal["all", "field"] = Field(description="Deletion scope.")
    field: str | None = Field(default=None, description="Field name (only for scope='field').")
    affected_rows: int = Field(description="Number of rows affected.")


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
    """Paginated-free listing of tokens owned by the current user."""

    tokens: list[HealthMetricTokenRow] = Field(default_factory=list, description="Tokens.")
