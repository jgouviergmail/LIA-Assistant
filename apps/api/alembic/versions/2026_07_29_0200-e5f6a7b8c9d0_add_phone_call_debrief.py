"""Add phone_calls.debrief (T01 structured call debrief).

UX Actions program, lot E: the post-call synthesis now extracts commitments,
follow-up tasks/reminders, a follow-up draft and uncertainties. Persisted so
the calls surface can re-display the debrief after a missed notification —
a conscious extension of the D-8 minimization (same retention: the reaper
clears it alongside summary/structured_data). See ADR-174.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-29 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable JSONB column — NULL for every pre-T01 call."""
    op.add_column(
        "phone_calls",
        sa.Column(
            "debrief",
            JSONB,
            nullable=True,
            comment=(
                "T01 structured debrief (commitments, follow_up_tasks, "
                "follow_up_reminders, follow_up_draft, uncertainties) — "
                "cleared by the retention reaper like summary (D-8)."
            ),
        ),
    )


def downgrade() -> None:
    """Drop the column — the debrief is re-derivable only from a new call."""
    op.drop_column("phone_calls", "debrief")
