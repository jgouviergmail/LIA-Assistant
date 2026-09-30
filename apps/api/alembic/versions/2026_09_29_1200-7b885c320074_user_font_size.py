"""Add the interface text size preference to users.

Revision ID: 7b885c320074
Revises: b138c047a5d2
Create Date: 2026-09-29 12:00:00.000000

The web client scales the document's root font size, so every rem of the UI
follows. Stored in CSS px at the browser's default root size; every existing
account reads the default (16), which is what it sees today. The bounds are the
range where the layout holds — mirrored by ``USER_FONT_SIZE_*_PX`` and restated
here as literals, since a migration must not move when a constant does.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7b885c320074"
down_revision: str | Sequence[str] | None = "b138c047a5d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "ck_users_font_size_range"


def upgrade() -> None:
    """Add ``users.font_size`` with its default and its bounds."""
    op.add_column(
        "users",
        sa.Column(
            "font_size",
            sa.SmallInteger(),
            nullable=False,
            server_default="16",
            comment="Interface text size in CSS px at the browser's default root size (14-20).",
        ),
    )
    op.create_check_constraint(_CONSTRAINT, "users", "font_size BETWEEN 14 AND 20")


def downgrade() -> None:
    """Drop the preference; the interface falls back to the browser's size."""
    op.drop_constraint(_CONSTRAINT, "users", type_="check")
    op.drop_column("users", "font_size")
