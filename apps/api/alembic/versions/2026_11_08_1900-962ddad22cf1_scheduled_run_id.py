"""Name the turn a routine run executed (ADR-375).

Revision ID: 962ddad22cf1
Revises: a4c92e7b6d81
Create Date: 2026-11-08 19:00:00.000000

A run row recorded WHEN a routine ran and how it ended, never WHICH turn it
ran: what the routine consulted could only be guessed from the instants it
overlapped, and routines due the same minute overlap. The run id joins the row
to the registers (``agent_treatments.run_id``, same width) exactly. Nullable:
rows written before this revision, and runs whose pipeline never started,
have no turn to name.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "962ddad22cf1"
down_revision: str | Sequence[str] | None = "a4c92e7b6d81"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable run id; existing rows keep NULL (no turn to name)."""
    op.add_column(
        "scheduled_action_runs",
        sa.Column(
            "run_id",
            sa.String(length=100),
            nullable=True,
            comment="The turn this run executed (joins the registers); NULL when it never ran.",
        ),
    )


def downgrade() -> None:
    """Drop the run id; the history rows themselves are untouched."""
    op.drop_column("scheduled_action_runs", "run_id")
