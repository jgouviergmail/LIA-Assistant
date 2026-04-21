"""Health Metrics domain database models.

Two tables:

- ``health_samples`` — polymorphic measurement samples. One row per unique
  `(user_id, kind, date_start, date_end)`. Supports two kinds initially —
  `"heart_rate"` (bpm) and `"steps"` (count) — with a CHECK constraint for
  forward compatibility. Client-supplied timestamps (date_start / date_end)
  are normalized to UTC before insertion so equal instants stored under
  different TZ offsets resolve to the same row via UPSERT.

- ``health_metric_tokens`` — per-user ingestion tokens. Only the SHA-256
  hash of the raw value is stored; the raw value is returned exactly once
  at creation time and never recoverable afterward. Multiple tokens may
  coexist per user and be revoked individually.

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
Revised: 2026-04-21 — migration to the polymorphic samples model.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.constants import HEALTH_METRICS_SOURCE_DEFAULT
from src.infrastructure.database.models import BaseModel


class HealthSample(BaseModel):
    """A single health measurement sample ingested from an external client.

    One row per unique ``(user_id, kind, date_start, date_end)`` tuple.
    Re-ingesting the same sample updates ``value`` and ``source`` in place
    (last-write-wins) via ON CONFLICT DO UPDATE.
    """

    __tablename__ = "health_samples"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="Discriminator: 'heart_rate' | 'steps'.",
    )

    date_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Start of the measurement interval (client-supplied, UTC-normalized).",
    )

    date_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="End of the measurement interval (client-supplied, UTC-normalized).",
    )

    value: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Numeric value for the kind (bpm for heart_rate, count for steps).",
    )

    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=HEALTH_METRICS_SOURCE_DEFAULT,
        comment="Origin label supplied per-sample (slugified, <= 32 chars).",
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('heart_rate', 'steps')",
            name="ck_health_samples_kind",
        ),
        UniqueConstraint(
            "user_id",
            "kind",
            "date_start",
            "date_end",
            name="uq_health_samples_user_kind_range",
        ),
        Index("ix_health_samples_user_kind_start", "user_id", "kind", "date_start"),
    )

    def __repr__(self) -> str:
        """Concise representation for logging."""
        return (
            f"<HealthSample(user_id={self.user_id}, kind={self.kind}, "
            f"start={self.date_start.isoformat() if self.date_start else None}, "
            f"value={self.value})>"
        )


class HealthMetricToken(BaseModel):
    """API token authorizing a client to POST to the ingestion endpoints.

    Only the SHA-256 hash of the token is persisted — the raw value is
    returned to the user exactly once at generation time. ``token_prefix``
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
