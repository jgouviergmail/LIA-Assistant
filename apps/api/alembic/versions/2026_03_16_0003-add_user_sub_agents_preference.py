"""Add sub_agents_enabled preference to users table.

Revision ID: sub_agents_003
Revises: sub_agents_002
Create Date: 2026-03-16

Per-user toggle for sub-agent delegation. Default: true (opt-out).
Users can disable sub-agent delegation in their settings.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "sub_agents_003"
down_revision: str | None = "sub_agents_002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add sub_agents_enabled column with default true."""
    op.add_column(
        "users",
        sa.Column(
            "sub_agents_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="User preference for sub-agent delegation (true = enabled)",
        ),
    )


def downgrade() -> None:
    """Remove sub_agents_enabled column."""
    op.drop_column("users", "sub_agents_enabled")
