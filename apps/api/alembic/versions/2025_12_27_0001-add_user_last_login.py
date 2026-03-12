"""Add user last_login tracking

Revision ID: add_user_last_login_001
Revises: add_user_voice_pref_001
Create Date: 2025-12-27 00:00:00.000000

This migration adds last_login field to users table for tracking last successful login.

The last_login timestamp is updated on each successful login (password or OAuth).
Useful for admin user management and identifying inactive users.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_user_last_login_001"
down_revision: str | None = "add_user_voice_pref_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Add last_login column to users table.
    """
    op.add_column(
        "users",
        sa.Column(
            "last_login",
            sa.DateTime(timezone=True),
            nullable=True,  # Null for users who never logged in
            comment="Timestamp of last successful login (OAuth or password).",
        ),
    )


def downgrade() -> None:
    """
    Remove last_login column.
    """
    op.drop_column("users", "last_login")
