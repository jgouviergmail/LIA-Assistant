"""Add user onboarding_completed preference.

Revision ID: add_onboarding_completed_001
Revises: add_interests_system_001
Create Date: 2026-01-28

This migration adds onboarding_completed field to users table.

The onboarding_completed preference tracks whether a user has completed
or dismissed the onboarding tutorial. Default is False (shows tutorial).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_onboarding_completed_001"
down_revision: str | None = "add_interests_system_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Add onboarding_completed column to users table.
    """
    op.add_column(
        "users",
        sa.Column(
            "onboarding_completed",
            sa.Boolean(),
            nullable=False,
            server_default="false",  # Shows tutorial by default
            comment="User has completed/dismissed the onboarding tutorial.",
        ),
    )


def downgrade() -> None:
    """
    Remove onboarding_completed column.
    """
    op.drop_column("users", "onboarding_completed")
