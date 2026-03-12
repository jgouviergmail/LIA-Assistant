"""Add user tokens_display_enabled preference.

Revision ID: add_user_tokens_display_001
Revises: add_system_settings_001
Create Date: 2026-01-16

This migration adds tokens_display_enabled field to users table.

The tokens_display_enabled preference allows users to toggle the display
of token usage and costs under assistant messages (desktop only).
Default is False (opt-in).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_user_tokens_display_001"
down_revision: str | None = "add_system_settings_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Add tokens_display_enabled column to users table.
    """
    op.add_column(
        "users",
        sa.Column(
            "tokens_display_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",  # Opt-in: disabled by default
            comment="User preference for displaying token usage and costs. False = disabled by default (opt-in).",
        ),
    )


def downgrade() -> None:
    """
    Remove tokens_display_enabled column.
    """
    op.drop_column("users", "tokens_display_enabled")
