"""Create health_metrics and health_metric_tokens tables.

Supports the Health Metrics feature: an iPhone Shortcut automation POSTs
heart rate + cumulative steps every hour to /api/v1/ingest/health. The
endpoint is authenticated by a per-user token (hashed in DB, raw value
shown once at generation).

Two new tables:
- health_metrics: one row per ingestion payload (nullable metric columns so
  mixed-validation NULLs survive alongside valid fields of the same row).
- health_metric_tokens: per-user SHA-256 hashed tokens with display prefix.

Revision ID: health_metrics_001
Revises: obs_indexes_001
Create Date: 2026-04-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "health_metrics_001"
down_revision: str | None = "obs_indexes_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create health_metrics and health_metric_tokens tables with indexes."""
    # =========================================================================
    # health_metrics — per-ingestion sample rows
    # =========================================================================
    op.create_table(
        "health_metrics",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Server-side reception timestamp (UTC).",
        ),
        sa.Column(
            "heart_rate",
            sa.SmallInteger(),
            nullable=True,
            comment="Last heart rate sample (bpm). NULL if not provided or out of range.",
        ),
        sa.Column(
            "steps_cumulative",
            sa.Integer(),
            nullable=True,
            comment="Cumulative daily step count. NULL if not provided or out of range.",
        ),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'unknown'"),
            comment="Origin label supplied by client (slugified, <= 32 chars).",
        ),
    )
    op.create_index(
        "ix_health_metrics_user_recorded",
        "health_metrics",
        ["user_id", "recorded_at"],
    )

    # =========================================================================
    # health_metric_tokens — per-user hashed API tokens
    # =========================================================================
    op.create_table(
        "health_metric_tokens",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "token_hash",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 hex digest of the raw token value.",
        ),
        sa.Column(
            "token_prefix",
            sa.String(length=16),
            nullable=False,
            comment="First N chars of the raw token for UI identification.",
        ),
        sa.Column(
            "label",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.UniqueConstraint("token_hash", name="uq_health_metric_tokens_hash"),
    )
    op.create_index(
        "ix_health_metric_tokens_user",
        "health_metric_tokens",
        ["user_id"],
    )


def downgrade() -> None:
    """Drop health metrics tables (cascade on user deletion already handled)."""
    op.drop_index("ix_health_metric_tokens_user", table_name="health_metric_tokens")
    op.drop_table("health_metric_tokens")
    op.drop_index("ix_health_metrics_user_recorded", table_name="health_metrics")
    op.drop_table("health_metrics")
