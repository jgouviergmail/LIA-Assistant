"""A kept answer remembers the turn that produced it, so it can show what it cost.

The bookmark showed one figure, the cost of INDEXING it into the « Kept
answers » space, which reads as the answer's own cost and is a few
thousandths of it. ``run_id`` is copied from the message at the click (a
bookmark is a copy, ADR-282) and joins the turn's ``message_token_summary``
row — the very row the chat bubble reads — so the answer's billed cost is
shown beside the indexing one, and the two can never disagree with the chat.

Existing bookmarks take the run id of their message when it still exists;
a bookmark whose conversation is gone keeps ``NULL`` (no figure, never a
guessed one).

Revision ID: b6e2d8f4a1c7
Revises: 3354f9ba30e2
Create Date: 2026-10-03 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6e2d8f4a1c7"
down_revision: str | None = "3354f9ba30e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RUN_ID_COMMENT = (
    "The run (turn) that produced the answer, copied at the click; joins "
    "message_token_summary for the answer's billed cost. NULL when unknown."
)


def upgrade() -> None:
    """Add the column, then fill it from the messages that still exist."""
    op.add_column(
        "message_bookmarks",
        sa.Column("run_id", sa.String(length=255), nullable=True, comment=_RUN_ID_COMMENT),
    )
    op.execute(sa.text("""
            UPDATE message_bookmarks AS b
               SET run_id = m.message_metadata ->> 'run_id'
              FROM conversation_messages AS m
             WHERE m.id = b.message_id
               AND b.run_id IS NULL
               AND m.message_metadata ->> 'run_id' IS NOT NULL
            """))


def downgrade() -> None:
    """Drop the column; the token summaries themselves are untouched."""
    op.drop_column("message_bookmarks", "run_id")
