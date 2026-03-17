"""Add system_disabled_skills column to users table.

Revision ID: system_disabled_skills_001
Revises: sub_agents_003
Create Date: 2026-03-17

System-level skill toggle for admins. Stores which system skills an admin
has disabled for all users. Separate from per-user disabled_skills
(personal preference).

NOTE: This column is dropped in the next migration (skills_tables_001)
which replaces it with normalized tables. This migration file is kept
for alembic revision chain integrity only.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "system_disabled_skills_001"
down_revision: str | None = "sub_agents_003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add system_disabled_skills JSONB column with default empty array."""
    op.add_column(
        "users",
        sa.Column(
            "system_disabled_skills",
            JSONB(),
            nullable=False,
            server_default="[]",
            comment="System skills disabled by admin (hidden for all non-superusers)",
        ),
    )


def downgrade() -> None:
    """Remove system_disabled_skills column."""
    op.drop_column("users", "system_disabled_skills")
