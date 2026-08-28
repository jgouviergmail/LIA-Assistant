"""Self-diagnostics persistence: health snapshots and incident memory.

Two tables for the diagnostics bounded context (spec 2026-08-27):

- ``health_snapshots`` — one row per self-check run (leader job, ~5 min);
  pruned by the job itself past the retention window, so growth is bounded.
- ``incidents`` — the incident memory. The partial unique index
  ``uq_incidents_open_correlation`` on ``(correlation_key) WHERE status =
  'open'`` is the concurrency contract: the Alertmanager webhook worker and
  the self-check leader can observe the same outage simultaneously and the
  open-or-touch upsert (ON CONFLICT on this index) still yields exactly one
  open incident per correlation key.

Both tables are inert while DIAGNOSTICS_ENABLED is false (nothing reads or
writes them), so this migration is safe on every deployment.

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-08-28 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a6b7c8d9e0f1"
down_revision: str | None = "f5a6b7c8d9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create health_snapshots and incidents with their indexes."""
    op.create_table(
        "health_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("overall", sa.String(length=16), nullable=False),
        sa.Column("results", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_health_snapshots_taken_at", "health_snapshots", ["taken_at"])

    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("correlation_key", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("alertname", sa.String(length=128), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("diagnosis", postgresql.JSONB(), nullable=True),
        sa.Column("action_log", postgresql.JSONB(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_opened_at", "incidents", ["opened_at"])
    op.create_index(
        "uq_incidents_open_correlation",
        "incidents",
        ["correlation_key"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    """Drop both tables (indexes go with them)."""
    op.drop_table("incidents")
    op.drop_table("health_snapshots")
