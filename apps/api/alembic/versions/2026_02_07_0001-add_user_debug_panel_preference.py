"""Add user debug_panel_enabled preference.

Revision ID: add_user_debug_panel_001
Revises: add_unaccent_ext_001
Create Date: 2026-02-07

This migration adds debug_panel_enabled field to users table.

The debug_panel_enabled preference controls whether the user has enabled
the debug panel feature. Default is False (disabled by default, opt-in).
Requires the admin system setting debug_panel_user_access_enabled to be
True for this user preference to have any effect.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_user_debug_panel_001"
down_revision: str | None = "add_unaccent_ext_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Add debug_panel_enabled column to users table.
    """
    op.add_column(
        "users",
        sa.Column(
            "debug_panel_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="User preference for debug panel. False = disabled by default (opt-in). Requires admin debug_panel_user_access_enabled.",
        ),
    )


def downgrade() -> None:
    """
    Remove debug_panel_enabled column.
    """
    op.drop_column("users", "debug_panel_enabled")
