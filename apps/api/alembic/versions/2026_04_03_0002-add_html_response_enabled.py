"""Add html_response_enabled preference to users.

Allows users to toggle styled HTML formatting of text responses
when data cards are disabled. Enabled by default.

Revision ID: html_response_001
Revises: cards_display_001
Create Date: 2026-04-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "html_response_001"
down_revision: str | None = "cards_display_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add html_response_enabled column with default True."""
    op.add_column(
        "users",
        sa.Column(
            "html_response_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="User preference for HTML-formatted responses when cards are disabled. True = enabled by default.",
        ),
    )


def downgrade() -> None:
    """Remove html_response_enabled column."""
    op.drop_column("users", "html_response_enabled")
