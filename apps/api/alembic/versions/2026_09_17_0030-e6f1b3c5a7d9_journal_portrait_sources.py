"""The portrait says what it was compiled from (2026-09-16 design, part B).

One nullable JSONB column on ``users``: the provenance the consolidation writes
WITH the portrait — the entries' count and, per source (memories, interests,
habits, relation_debriefs), what it answered. NULL until the next compilation.

Revision ID: e6f1b3c5a7d9
Revises: d5e0a2b4f6c8
Create Date: 2026-09-17 00:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e6f1b3c5a7d9"
down_revision: str | None = "d5e0a2b4f6c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMENT = (
    "Provenance of the compiled portrait: journal entries count and, per source "
    "(memories, interests, habits, relation_debriefs), status/used/total."
)


def upgrade() -> None:
    """Add the provenance column, NULL for everyone until the next compilation."""
    op.add_column(
        "users",
        sa.Column(
            "journal_portrait_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=_COMMENT,
        ),
    )


def downgrade() -> None:
    """Drop the column; the portrait itself stays."""
    op.drop_column("users", "journal_portrait_sources")
