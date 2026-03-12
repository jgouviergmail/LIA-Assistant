"""Add user theme preferences.

Revision ID: add_user_theme_prefs_001
Revises: add_fcm_tokens_001
Create Date: 2026-01-10

This migration adds theme and color_theme fields to users table
for per-user display preferences that persist across devices.

- theme: 'light', 'dark', or 'system' (display mode)
- color_theme: 'default', 'ocean', 'forest', 'sunset', 'slate' (color palette)
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_user_theme_prefs_001"
down_revision: str | None = "add_fcm_tokens_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Add theme and color_theme columns to users table.
    """
    op.add_column(
        "users",
        sa.Column(
            "theme",
            sa.String(20),
            nullable=False,
            server_default="system",
            comment="User display mode preference: 'light', 'dark', or 'system' (follow OS).",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "color_theme",
            sa.String(20),
            nullable=False,
            server_default="default",
            comment="User color theme preference: 'default', 'ocean', 'forest', 'sunset', 'slate'.",
        ),
    )


def downgrade() -> None:
    """
    Remove theme and color_theme columns.
    """
    op.drop_column("users", "color_theme")
    op.drop_column("users", "theme")
