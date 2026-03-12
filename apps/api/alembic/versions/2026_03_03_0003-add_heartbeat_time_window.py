"""Add dedicated heartbeat notification time window.

Revision ID: heartbeat_002
Revises: heartbeat_001
Create Date: 2026-03-03

Add 2 user columns for heartbeat-specific notification time window,
independent from interests notification hours.

Phase: evolution F5 — Heartbeat Autonome LLM
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "heartbeat_002"
down_revision: str | None = "heartbeat_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add heartbeat notification time window columns to users."""
    op.add_column(
        "users",
        sa.Column(
            "heartbeat_notify_start_hour",
            sa.Integer,
            nullable=False,
            server_default=sa.text("9"),
            comment="Start hour (0-23) for heartbeat notification window.",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "heartbeat_notify_end_hour",
            sa.Integer,
            nullable=False,
            server_default=sa.text("22"),
            comment="End hour (0-23) for heartbeat notification window.",
        ),
    )


def downgrade() -> None:
    """Remove heartbeat notification time window columns."""
    op.drop_column("users", "heartbeat_notify_end_hour")
    op.drop_column("users", "heartbeat_notify_start_hour")
