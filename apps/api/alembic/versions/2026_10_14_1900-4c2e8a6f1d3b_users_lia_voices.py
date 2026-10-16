"""The voices LIA speaks with for one person, per voice engine (ADR-345 amendment 2026-10-14).

Revision ID: 4c2e8a6f1d3b
Revises: 8ba7655b548b
Create Date: 2026-10-14 19:00:00.000000

A person chooses LIA's male and female voice in the voice mode settings; the
choice is kept per engine (the voice slot's provider and model) on their own
row, NULL until they choose. Nothing is backfilled: every account speaks with
the instance's voices until its person chooses others.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "4c2e8a6f1d3b"
down_revision: str | None = "8ba7655b548b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMENT = (
    "The voices LIA speaks with in the chat for this account, per voice engine "
    "(provider/model): {engine: {male, female}}. A gender left out speaks with the "
    "instance's voice."
)


def upgrade() -> None:
    """Add the nullable column."""
    op.add_column(
        "users",
        sa.Column("lia_voices", postgresql.JSONB(), nullable=True, comment=_COMMENT),
    )


def downgrade() -> None:
    """Drop the column: the choices go with it."""
    op.drop_column("users", "lia_voices")
