"""Add an optional JSONB ``context_biometric`` column to ``memories``.

Lets the memory extractor enrich a memory with a compact Health Metrics
snapshot (baseline deltas, trends, events) at capture time, *only* when
the user has opted into Health Metrics assistant integrations *and* the
emotional weight meets the threshold. Never stores raw sensor values.

The column is nullable — existing rows stay untouched.

Revision ID: health_metrics_005
Revises: health_metrics_004
Create Date: 2026-04-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "health_metrics_005"
down_revision: str | None = "health_metrics_004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the ``context_biometric`` JSONB column."""
    op.add_column(
        "memories",
        sa.Column(
            "context_biometric",
            JSONB(),
            nullable=True,
            comment=(
                "Optional Health Metrics snapshot captured at extraction time "
                "(baseline deltas, trends, events — never raw values)."
            ),
        ),
    )


def downgrade() -> None:
    """Drop the ``context_biometric`` JSONB column."""
    op.drop_column("memories", "context_biometric")
