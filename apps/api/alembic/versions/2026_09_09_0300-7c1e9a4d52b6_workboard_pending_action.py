"""workboard: the draft a ticket waits on (ADR-276, lot 7)

Revision ID: 7c1e9a4d52b6
Revises: 02d23dd84146
Create Date: 2026-09-09 03:00:00

A run that meets an action it may not perform unattended no longer refuses it:
it builds the draft the chat would have shown, and the TICKET carries it while
the person decides. One nullable JSONB column: ``{draft_id, draft_type,
draft_content, tool_name, question, approved}``. Cleared when the person
refuses, amends, or when the approved draft has run.

No CHECK and no index: the column is read by the ticket's own row and nothing
scans it — the board finds these tickets by their ``confirming`` status, which
the existing owner/assignee status indexes already cover.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "7c1e9a4d52b6"
down_revision = "02d23dd84146"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workboard_tickets",
        sa.Column(
            "pending_action",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "The draft the person must confirm on the ticket (lot 7): "
                "draft_id, draft_type, draft_content, tool_name, question, approved."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("workboard_tickets", "pending_action")
