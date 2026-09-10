"""Rows of an out-of-turn run, kept in full and left out of the chat (ADR-276).

A ticket LIA executes runs through the person's ordinary pipeline, on their
ordinary conversation thread, and archives its two rows exactly like any turn.
That is not incidental: archive-first (ADR-117) persists the question BEFORE
the graph runs so a crash cannot lose the turn, and the decision register
(ADR-263, lot 6) points at the request and the answer with ``SET NULL``
tombstones — a run that archived nothing would leave a register row that reads
exactly like a deleted conversation.

So the record stays whole and one boolean decides what the CHAT shows. A
column rather than a metadata key: the chat history is the hottest read in the
application, and a JSONB test there would cost a parse per row where a column
costs the pagination index a filter.

Revision ID: 691135cc728c
Revises: 99b7098a892f
Create Date: 2026-09-09 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "691135cc728c"
down_revision: str | None = "99b7098a892f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the visibility flag every chat read now applies."""
    op.add_column(
        "conversation_messages",
        sa.Column(
            "hidden",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Row of an out-of-turn run: kept in full, excluded from the chat read.",
        ),
    )


def downgrade() -> None:
    """Drop the flag; every row becomes visible again."""
    op.drop_column("conversation_messages", "hidden")
