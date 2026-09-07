"""What the call that wrote a debrief cost, stored beside the words.

A separate revision rather than an edit to `625745c6e5ee`: that one has run,
and the table it created already holds debriefs. Recreating it to add a column
would destroy them — and "the column arrived after the table" is what actually
happened, so the history says it.

The column is a DISPLAY summary, never an accounting record: `token_usage_logs`
holds one row per call, outlives the account, and is one of the five sources the
Article-12 extraction composes. Anything that ADDS costs up reads that. This
only ever describes the one call whose words sit next to it — which is why it is
one JSONB column and not four numeric ones nobody could resist summing.

Nullable, and it stays nullable: a debrief written before this existed made no
claim about its cost, and backfilling a zero would invent one.

Revision ID: 00fae77284aa
Revises: 625745c6e5ee
Create Date: 2026-09-07 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "00fae77284aa"
down_revision: str | None = "625745c6e5ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the per-build usage summary."""
    op.add_column(
        "relation_debriefs",
        sa.Column(
            "usage",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="What the call that wrote the body cost (display summary, not an account).",
        ),
    )


def downgrade() -> None:
    """Drop it."""
    op.drop_column("relation_debriefs", "usage")
