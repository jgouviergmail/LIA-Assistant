"""Add user font_family preference.

Revision ID: add_user_font_family_001
Revises: add_user_tokens_display_001
Create Date: 2026-01-26

This migration adds font_family field to users table.

The font_family preference allows users to customize the display font
across the entire interface. Default is 'system' (Inter font).

Valid values: system, noto-sans, plus-jakarta-sans, ibm-plex-sans,
              geist, source-sans-pro, merriweather, libre-baskerville, fira-code
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_user_font_family_001"
down_revision: str | None = "add_user_tokens_display_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Add font_family column to users table.
    """
    op.add_column(
        "users",
        sa.Column(
            "font_family",
            sa.String(30),
            nullable=False,
            server_default="system",
            comment="User font family preference: system, noto-sans, plus-jakarta-sans, ibm-plex-sans, geist, source-sans-pro, merriweather, libre-baskerville, fira-code.",
        ),
    )


def downgrade() -> None:
    """
    Remove font_family column.
    """
    op.drop_column("users", "font_family")
