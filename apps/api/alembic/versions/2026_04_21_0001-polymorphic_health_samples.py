"""Replace health_metrics with polymorphic health_samples.

The ingestion contract changes from a per-POST bundle (HR + steps together,
server-timestamped at reception) to batches of per-sample events (steps or
HR separately, client-timestamped with date_start/date_end intervals).
Re-ingesting the same sample is idempotent via UPSERT on
(user_id, kind, date_start, date_end).

Because the feature flag is `false` in prod and only demo data exists in
dev, we DROP the old table instead of attempting a data migration.

Revision ID: health_metrics_003
Revises: health_metrics_002
Create Date: 2026-04-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "health_metrics_003"
down_revision: str | None = "health_metrics_002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the singleton-style table and create the polymorphic samples table."""
    op.drop_index(
        "ix_health_metrics_user_recorded",
        table_name="health_metrics",
        if_exists=True,
    )
    op.drop_table("health_metrics")

    op.create_table(
        "health_samples",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kind",
            sa.String(length=16),
            nullable=False,
            comment="Discriminator: 'heart_rate' | 'steps'.",
        ),
        sa.Column(
            "date_start",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Start of the measurement interval (client-supplied, UTC-normalized).",
        ),
        sa.Column(
            "date_end",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="End of the measurement interval (client-supplied, UTC-normalized).",
        ),
        sa.Column(
            "value",
            sa.Integer(),
            nullable=False,
            comment="Numeric value for the kind (bpm for heart_rate, count for steps).",
        ),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'iphone'"),
            comment="Origin label supplied per-sample (slugified, <= 32 chars).",
        ),
        sa.CheckConstraint(
            "kind IN ('heart_rate', 'steps')",
            name="ck_health_samples_kind",
        ),
        sa.UniqueConstraint(
            "user_id",
            "kind",
            "date_start",
            "date_end",
            name="uq_health_samples_user_kind_range",
        ),
    )
    op.create_index(
        "ix_health_samples_user_kind_start",
        "health_samples",
        ["user_id", "kind", "date_start"],
    )


def downgrade() -> None:
    """Recreate the legacy singleton table (data NOT restored)."""
    op.drop_index("ix_health_samples_user_kind_start", table_name="health_samples")
    op.drop_table("health_samples")

    op.create_table(
        "health_metrics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heart_rate", sa.SmallInteger(), nullable=True),
        sa.Column("steps", sa.Integer(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
    )
    op.create_index(
        "ix_health_metrics_user_recorded",
        "health_metrics",
        ["user_id", "recorded_at"],
    )
