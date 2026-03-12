"""Add user voice_mode_enabled preference.

Revision ID: add_voice_mode_enabled_001
Revises: add_admin_broadcast_001
Create Date: 2026-02-01

This migration adds voice_mode_enabled field to users table.

The voice_mode_enabled preference controls whether the user has enabled
the voice mode feature (wake word detection + STT input). Default is False
(text input mode, no voice activation).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_voice_mode_enabled_001"
down_revision: str | None = "add_admin_broadcast_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Add voice_mode_enabled column to users table.
    """
    op.add_column(
        "users",
        sa.Column(
            "voice_mode_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",  # Disabled by default (opt-in)
            comment="User preference for voice mode (wake word + STT input). False = disabled by default (opt-in).",
        ),
    )


def downgrade() -> None:
    """
    Remove voice_mode_enabled column.
    """
    op.drop_column("users", "voice_mode_enabled")
