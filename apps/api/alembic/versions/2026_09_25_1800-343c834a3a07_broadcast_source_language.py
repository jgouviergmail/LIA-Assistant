"""A broadcast stores the language it is translated from (ADR-323).

Revision ID: 343c834a3a07
Revises: 6c871f348887
Create Date: 2026-09-25 18:00:00.000000

The send route never passed a source language, so every broadcast was
translated FROM French whatever the administrator wrote: written in English,
its English original reached the French readers untranslated (the source group
receives the original) and every other group got a translation of a text
mislabelled as French. The source language is now the administrator's own —
the language their request declares — and it is STORED, because a late read
(a language group absent at send time) translates from it.

The backfill writes ``fr`` on every existing row: that is how each of them was
treated when it was sent — the only source language the code ever used — so
the label is historical truth, not a guess about what an administrator typed.

Downgrade drops the column: the previous code reads nothing of it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "343c834a3a07"
down_revision: str | None = "6c871f348887"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMENT = (
    "Language every translation is made from, at send time and on a late "
    "read: the sending admin's account language (ADR-323)"
)

#: Read by the integration test too, so what it proves is what the upgrade runs.
BACKFILL_STATEMENT = "UPDATE admin_broadcasts SET source_language = 'fr' WHERE source_language IS NULL"


def upgrade() -> None:
    """Add the column, label every existing row, then require it."""
    op.add_column(
        "admin_broadcasts",
        sa.Column("source_language", sa.String(length=10), nullable=True, comment=_COMMENT),
    )
    op.execute(BACKFILL_STATEMENT)
    op.alter_column(
        "admin_broadcasts",
        "source_language",
        existing_type=sa.String(length=10),
        existing_comment=_COMMENT,
        nullable=False,
    )


def downgrade() -> None:
    """Drop the column."""
    op.drop_column("admin_broadcasts", "source_language")
