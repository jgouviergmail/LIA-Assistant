"""A listener's interests are a source of stories, never read by the newsroom (ADR-324).

Revision ID: 73f828799cdf
Revises: 4c1e8b2f9a37
Create Date: 2026-09-28 09:00:00.000000

The stories a search finds for a listener's interests are filed like any other, under
a row of their own in ``radio_feeds`` (``kind = 'interest'``), so the shortlists, the
aired ledger, the article page and the retention read them unchanged; the newsroom
reads the ``source`` rows alone (decision 40). A story found by a search comes from
its own outlet, not its row's: ``radio_news_items.outlet`` names it (NULL = the
feed's, as every story before).

The downgrade removes the interest rows first — their stories go with them by the
foreign key's cascade — so the previous release never meets a row it would read.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "73f828799cdf"
down_revision: str | None = "4c1e8b2f9a37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KIND_COMMENT = (
    "source: a feed the newsroom reads (the catalogue's, or a listener's site); "
    "interest: the stories a search found for its owner's interests, never read."
)
_ITEM_OUTLET_COMMENT = (
    "The outlet that published the story, when not its feed's; NULL = the feed's."
)


def upgrade() -> None:
    """Add the feed's kind and the story's own outlet."""
    op.add_column(
        "radio_feeds",
        sa.Column(
            "kind",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'source'"),
            comment=_KIND_COMMENT,
        ),
    )
    op.add_column(
        "radio_news_items",
        sa.Column("outlet", sa.String(160), nullable=True, comment=_ITEM_OUTLET_COMMENT),
    )


def downgrade() -> None:
    """Remove the interest rows (their stories cascade), then both columns."""
    op.execute(sa.text("DELETE FROM radio_feeds WHERE kind = 'interest'"))
    op.drop_column("radio_news_items", "outlet")
    op.drop_column("radio_feeds", "kind")
