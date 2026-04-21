"""Health Metrics domain database models.

Defines the persistence layer for:
- HealthMetric: one row per received ingestion payload, per-field nullable
  columns (a row can carry heart_rate only, steps only, or both) plus a
  free-form `source` label. Rows are immutable after insertion; deletions
  are performed as column-level UPDATE (field=NULL) or full row DELETE
  depending on the user-requested deletion scope.
- HealthMetricToken: per-user ingestion tokens. Only the SHA-256 hash is
  stored; the raw token value is returned once at creation time and never
  recoverable afterward. A user may hold several active tokens concurrently
  (rotation use case) and revoke any of them independently.

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.constants import HEALTH_METRICS_SOURCE_DEFAULT
from src.infrastructure.database.models import BaseModel


class HealthMetric(BaseModel):
    """A single health metric sample ingested from an external client.

    One row per POST /api/v1/ingest/health. Columns are nullable so that a
    row can carry a subset of metrics (mixed per-field validation may NULL
    out an invalid field while preserving valid siblings in the same row).
    """

    __tablename__ = "health_metrics"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Server-side reception timestamp (UTC). Authoritative horodatage.",
    )

    heart_rate: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="Last heart rate sample (bpm). NULL if not provided or out of range.",
    )

    steps: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment=(
            "Steps recorded during the inter-sample period "
            "(NOT a daily cumulative counter). NULL if not provided or out of range."
        ),
    )

    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=HEALTH_METRICS_SOURCE_DEFAULT,
        comment="Origin label supplied by client (slugified, <= 32 chars).",
    )

    __table_args__ = (Index("ix_health_metrics_user_recorded", "user_id", "recorded_at"),)

    def __repr__(self) -> str:
        """Concise representation for logging."""
        return (
            f"<HealthMetric(user_id={self.user_id}, "
            f"recorded_at={self.recorded_at.isoformat() if self.recorded_at else None}, "
            f"hr={self.heart_rate}, steps={self.steps})>"
        )


class HealthMetricToken(BaseModel):
    """API token authorizing a client to POST to the ingestion endpoint.

    Only the SHA-256 hash of the token is persisted — the raw value is
    returned to the user exactly once at generation time. `token_prefix`
    stores the first N characters for UI display ("hm_abcdef…"), letting
    the user identify the token without exposing the secret material.
    """

    __tablename__ = "health_metric_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="SHA-256 hex digest of the raw token value (never the raw token).",
    )

    token_prefix: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="First N chars of the raw token for UI identification (non-secret).",
    )

    label: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Optional user-supplied label (e.g. 'iPhone perso').",
    )

    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Updated on each successful ingestion.",
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Set when user revokes the token. Revoked tokens are never reactivated.",
    )

    __table_args__ = (Index("ix_health_metric_tokens_user", "user_id"),)

    def __repr__(self) -> str:
        """Concise representation for logging."""
        return (
            f"<HealthMetricToken(user_id={self.user_id}, "
            f"prefix={self.token_prefix}, revoked={self.revoked_at is not None})>"
        )
