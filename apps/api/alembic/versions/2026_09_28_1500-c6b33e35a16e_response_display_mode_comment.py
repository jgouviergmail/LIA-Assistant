"""Align the response display mode comment with the HTML plus cards option.

Revision ID: c6b33e35a16e
Revises: 73f828799cdf
Create Date: 2026-09-28 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c6b33e35a16e"
down_revision: str | Sequence[str] | None = "73f828799cdf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_COMMENT = (
    "Response display mode: cards (HTML data cards), html (rich formatting), "
    "markdown (plain text)."
)
_NEW_COMMENT = (
    "Response display mode: cards (HTML data cards), html (rich formatting), "
    "html_cards (rich HTML with selected data cards), markdown (plain text)."
)


def upgrade() -> None:
    """Document every response display mode in the schema."""
    op.alter_column(
        "users",
        "response_display_mode",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        existing_server_default=sa.text("'cards'"),
        comment=_NEW_COMMENT,
        existing_comment=_OLD_COMMENT,
    )


def downgrade() -> None:
    """Restore the former column comment."""
    op.alter_column(
        "users",
        "response_display_mode",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        existing_server_default=sa.text("'cards'"),
        comment=_OLD_COMMENT,
        existing_comment=_NEW_COMMENT,
    )
