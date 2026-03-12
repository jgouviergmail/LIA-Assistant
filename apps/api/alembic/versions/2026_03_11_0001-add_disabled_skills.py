"""Add disabled_skills column to users table.

Revision ID: skills_002
Revises: heartbeat_003
Create Date: 2026-03-11

Per-user skill toggle: users can disable individual admin or user skills.
Pattern: admin_mcp_disabled_servers (evolution F2.5).

Phase: Skills — Per-user skill toggle
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "skills_002"
down_revision: str | None = "heartbeat_003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "disabled_skills",
            JSONB,
            nullable=False,
            server_default="[]",
            comment="List of skill names disabled by this user (e.g., ['briefing-quotidien'])",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "disabled_skills")
