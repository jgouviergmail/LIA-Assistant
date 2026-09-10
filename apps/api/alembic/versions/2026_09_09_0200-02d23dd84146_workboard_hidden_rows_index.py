"""workboard: a partial index over the hidden run rows

Two readers need the same small set and would otherwise scan the whole message
table for it (ADR-276):

- the retention sweep, which deletes the transcripts of tickets closed past the
  window — once a minute, for ever;
- the volume gauges (``lia_hidden_run_rows`` / ``lia_hidden_run_bytes``), which
  exist because the owner accepted archiving a run's rows on the condition that
  the growth be WATCHED rather than assumed.

PARTIAL on purpose: the vast majority of a conversation is visible, and an
index carrying it would cost more than the reads it serves. ``created_at`` is
the indexed column so the sweep can also read the oldest hidden rows in order.

Revision ID: 02d23dd84146
Revises: 691135cc728c
Create Date: 2026-09-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "02d23dd84146"
down_revision: str | None = "691135cc728c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "ix_conversation_messages_hidden"


def upgrade() -> None:
    """Create the partial index over hidden rows."""
    op.create_index(
        INDEX_NAME,
        "conversation_messages",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("hidden"),
    )


def downgrade() -> None:
    """Drop it."""
    op.drop_index(INDEX_NAME, table_name="conversation_messages")
