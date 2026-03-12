"""Add heartbeat_min_per_day column to users.

Revision ID: heartbeat_003
Revises: widen_connector_type_001
Create Date: 2026-03-10

Aligns heartbeat with interests pattern: user can configure both
min_per_day and max_per_day for proactive notification frequency.
Previously min was hardcoded to 1 via getattr fallback.

Phase: evolution F5 — Heartbeat Autonome LLM
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "heartbeat_003"
down_revision: str | None = "widen_connector_type_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add heartbeat_min_per_day column to users."""
    op.add_column(
        "users",
        sa.Column(
            "heartbeat_min_per_day",
            sa.Integer,
            nullable=False,
            server_default=sa.text("1"),
            comment="Minimum heartbeat notifications per day (1-8).",
        ),
    )


def downgrade() -> None:
    """Remove heartbeat_min_per_day column."""
    op.drop_column("users", "heartbeat_min_per_day")
