"""Rename psyche_display_mood to psyche_display_avatar.

Semantic change: the setting now controls the emotional avatar display
in chat messages (personality emoji + mood smiley) instead of the
header mood ring (which is being removed).

Revision ID: psyche_avatar_001
Revises: psyche_engine_001
Create Date: 2026-04-01 12:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "psyche_avatar_001"
down_revision: str | None = "psyche_engine_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename psyche_display_mood column to psyche_display_avatar."""
    op.alter_column(
        "users",
        "psyche_display_mood",
        new_column_name="psyche_display_avatar",
        comment="Display emotional avatar (personality + mood smiley) in chat messages.",
    )


def downgrade() -> None:
    """Revert: rename psyche_display_avatar back to psyche_display_mood."""
    op.alter_column(
        "users",
        "psyche_display_avatar",
        new_column_name="psyche_display_mood",
        comment="Display mood indicator ring around personality emoji in UI.",
    )
