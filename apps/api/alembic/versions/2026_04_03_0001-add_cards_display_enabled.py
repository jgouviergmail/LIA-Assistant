"""Add cards_display_enabled preference to users.

Allows users to toggle HTML data cards (contacts, events, emails,
weather, etc.) in assistant responses. Enabled by default.

Revision ID: cards_display_001
Revises: keyword_embedding_001
Create Date: 2026-04-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cards_display_001"
down_revision: str | None = "keyword_embedding_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add cards_display_enabled column with default True."""
    op.add_column(
        "users",
        sa.Column(
            "cards_display_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="User preference for HTML data cards in responses. True = enabled by default.",
        ),
    )


def downgrade() -> None:
    """Remove cards_display_enabled column."""
    op.drop_column("users", "cards_display_enabled")
