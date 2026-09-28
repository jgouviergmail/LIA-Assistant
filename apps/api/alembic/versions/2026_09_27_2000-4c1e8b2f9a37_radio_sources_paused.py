"""A listener's own site can be paused; the catalogue's kinds of news are gone (ADR-324).

Revision ID: 4c1e8b2f9a37
Revises: 70fd39bf9e8d
Create Date: 2026-09-27 20:00:00.000000

A listener pauses one of their own sites rather than deleting it: the newsroom stops
reading it and no session is offered its stories (``radio_feeds.paused``, meaningful on
the rows a listener owns). The catalogue's kind of journalism (``radio_feeds.category``)
had one reader, the settings' kinds of news, which left with the owner's decision of
2026-09-27 — everything airs translated, and every base source is ticked by default.

The downgrade restores the column empty: the previous release's catalogue sync fills it
again at its next pass.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4c1e8b2f9a37"
down_revision: str | None = "70fd39bf9e8d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PAUSED_COMMENT = "Whether the listener paused their own site: not read, not offered."
_CATEGORY_COMMENT = "The catalogue's kind of journalism; NULL for a listener's own site."


def upgrade() -> None:
    """Add the pause, drop the kind."""
    op.add_column(
        "radio_feeds",
        sa.Column(
            "paused",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment=_PAUSED_COMMENT,
        ),
    )
    op.drop_column("radio_feeds", "category")


def downgrade() -> None:
    """Restore the kind (empty until the catalogue sync), drop the pause."""
    op.add_column(
        "radio_feeds",
        sa.Column("category", sa.String(32), nullable=True, comment=_CATEGORY_COMMENT),
    )
    op.drop_column("radio_feeds", "paused")
