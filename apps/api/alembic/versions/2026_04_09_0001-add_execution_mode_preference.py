"""Add execution_mode preference to users table.

Supports pipeline (classic planner) and react (ReAct agent loop) execution modes.
Default: 'pipeline' for backward compatibility.

Revision ID: execution_mode_001
Revises: display_mode_001
Create Date: 2026-04-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "execution_mode_001"
down_revision: str | None = "display_mode_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add execution_mode column to users table."""
    op.add_column(
        "users",
        sa.Column(
            "execution_mode",
            sa.String(20),
            nullable=False,
            server_default="pipeline",
            comment="Execution mode preference: 'pipeline' (classic planner) or 'react' (ReAct agent loop).",
        ),
    )


def downgrade() -> None:
    """Remove execution_mode column from users table."""
    op.drop_column("users", "execution_mode")
