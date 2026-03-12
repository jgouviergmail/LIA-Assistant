"""Add user voice preference for TTS

Revision ID: add_user_voice_pref_001
Revises: add_user_memory_pref_001
Create Date: 2025-12-24 00:00:00.000000

This migration adds voice_enabled field to users table for per-user TTS control.

The voice_enabled preference allows users to toggle voice comments (TTS)
via UI toggle in header. Default is False (opt-in).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_user_voice_pref_001"
down_revision: str | None = "add_user_memory_pref_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Add voice_enabled column to users table.
    """
    op.add_column(
        "users",
        sa.Column(
            "voice_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",  # Opt-in: disabled by default
            comment="User preference for voice comments (TTS). False = disabled by default (opt-in).",
        ),
    )


def downgrade() -> None:
    """
    Remove voice_enabled column.
    """
    op.drop_column("users", "voice_enabled")
