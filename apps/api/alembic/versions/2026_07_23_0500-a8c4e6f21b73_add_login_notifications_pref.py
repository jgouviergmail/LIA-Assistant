"""Add users.login_notifications_enabled (security program D2, A4).

Preference gating the new-login FCM notification sent when a session is
created from a device that did not attest itself (no valid FCM token at
login). Default TRUE — security-first on a publicly exposed instance.

Revision ID: a8c4e6f21b73
Revises: f7b2d8e14a59
Create Date: 2026-07-23 05:00:00
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "a8c4e6f21b73"
down_revision = "f7b2d8e14a59"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the new-login notification preference column."""
    op.add_column(
        "users",
        sa.Column(
            "login_notifications_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
            comment="Notify the user's devices (FCM) on logins from unattested devices.",
        ),
    )


def downgrade() -> None:
    """Drop the preference column."""
    op.drop_column("users", "login_notifications_enabled")
