"""Paid speech synthesis on the run's own row (ADR-324).

Revision ID: d79c9fc26844
Revises: d3927d79b1df
Create Date: 2026-09-26 15:00:00.000000

``message_token_summary`` is the one row a run's cost is read from — the chat
meter, the phone bill, the live closing card, and now a radio session's live
cost. Paid speech synthesis never reached it: the chat kept each answer's
share on the assistant bubble alone, and a radio session has no bubble. Two
columns carry it now, filled by the same UPSERT as every other family.

The backfill copies what the bubbles already hold, summed per run (a turn
resumed after a question keeps its run id, so two bubbles may share one row).
A bubble whose run has no row stays as it is: nothing is invented.

The downgrade drops the two columns: the chat's shares remain on their
bubbles and in ``user_statistics``; a radio session's synthesis is then only
in ``user_statistics``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d79c9fc26844"
down_revision: str | None = "d3927d79b1df"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: The bubbles' shares summed per run, onto the run's row — the statement the
#: upgrade runs, and the one its PostgreSQL test runs.
BACKFILL_STATEMENT = """
UPDATE message_token_summary AS summary
SET tts_characters = spoken.characters,
    tts_cost_eur = spoken.cost_eur
FROM (
    SELECT message_metadata ->> 'run_id' AS run_id,
           SUM(COALESCE(tts_characters, 0))::integer AS characters,
           SUM(COALESCE(tts_cost_eur, 0)) AS cost_eur
    FROM conversation_messages
    WHERE tts_provider IS NOT NULL
      AND message_metadata ->> 'run_id' IS NOT NULL
    GROUP BY message_metadata ->> 'run_id'
) AS spoken
WHERE summary.run_id = spoken.run_id
"""


def upgrade() -> None:
    """Add the two columns and copy the bubbles' shares onto their runs."""
    op.add_column(
        "message_token_summary",
        sa.Column("tts_characters", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "message_token_summary",
        sa.Column("tts_cost_eur", sa.Numeric(10, 6), nullable=False, server_default=sa.text("0")),
    )
    op.execute(BACKFILL_STATEMENT)


def downgrade() -> None:
    """Drop the two columns (the chat's shares remain on their bubbles)."""
    op.drop_column("message_token_summary", "tts_cost_eur")
    op.drop_column("message_token_summary", "tts_characters")
