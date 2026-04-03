"""Replace cards_display_enabled + html_response_enabled with response_display_mode.

Simplifies two boolean display preferences into a single enum-like
string field: 'cards' (default), 'html', or 'markdown'.

Revision ID: display_mode_001
Revises: html_response_001
Create Date: 2026-04-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "display_mode_001"
down_revision: str | None = "html_response_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add response_display_mode and drop old boolean columns."""
    # Add new column with default
    op.add_column(
        "users",
        sa.Column(
            "response_display_mode",
            sa.String(20),
            nullable=False,
            server_default="cards",
            comment="Response display mode: cards, html, or markdown.",
        ),
    )

    # Migrate data: map old booleans to new mode
    op.execute(
        sa.text("""
            UPDATE users SET response_display_mode = CASE
                WHEN cards_display_enabled = true THEN 'cards'
                WHEN html_response_enabled = true THEN 'html'
                ELSE 'markdown'
            END
        """)
    )

    # Drop old columns
    op.drop_column("users", "html_response_enabled")
    op.drop_column("users", "cards_display_enabled")


def downgrade() -> None:
    """Restore boolean columns from response_display_mode."""
    op.add_column(
        "users",
        sa.Column(
            "cards_display_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "html_response_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # Migrate data back
    op.execute(
        sa.text("""
            UPDATE users SET
                cards_display_enabled = (response_display_mode = 'cards'),
                html_response_enabled = (response_display_mode IN ('cards', 'html'))
        """)
    )

    op.drop_column("users", "response_display_mode")
