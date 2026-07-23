"""Add users.briefing_preferences (UXR Lot 5, B4).

Per-user visibility + ordering of the 9 dashboard briefing cards. Nullable
JSONB — NULL keeps the historical behavior (all cards visible, canonical
order), so existing users need no backfill. Writes are full NEW-dict
replacements (JSONB new-dict rule).

Revision ID: b7e3d9c41a56
Revises: a4f7c2e91b3d
Create Date: 2026-07-23 01:00:00
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision = "b7e3d9c41a56"
down_revision = "a4f7c2e91b3d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the nullable JSONB preferences column."""
    op.add_column(
        "users",
        sa.Column(
            "briefing_preferences",
            JSONB,
            nullable=True,
            comment=(
                "Briefing grid preferences: {hidden: [...], order: [...]} — "
                "NULL = all cards visible in canonical order (UXR B4)."
            ),
        ),
    )


def downgrade() -> None:
    """Drop the preferences column."""
    op.drop_column("users", "briefing_preferences")
