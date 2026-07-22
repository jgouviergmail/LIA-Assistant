"""create open_loops table

Commitments ledger (P5, ADR-139): tracked commitments extracted from
conversation — things the user owes someone (user_owes) and things the
user is waiting on (waiting_on_other). Nudged through the heartbeat with
a per-loop cooldown; soft-expired lazily after prolonged inactivity.

Revision ID: a4f7c2e91b3d
Revises: 0ef84488b15c
Create Date: 2026-07-22 10:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "a4f7c2e91b3d"
down_revision = "0ef84488b15c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the open_loops table + hot-path partial index."""
    op.create_table(
        "open_loops",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subject",
            sa.Text(),
            nullable=False,
            comment="What the commitment is about, in the user's language.",
        ),
        sa.Column(
            "counterparty",
            sa.Text(),
            nullable=True,
            comment="Person or organization on the other side of the loop.",
        ),
        sa.Column(
            "direction",
            sa.String(length=20),
            nullable=False,
            comment="user_owes | waiting_on_other (OpenLoopDirection).",
        ),
        sa.Column(
            "due_hint",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Best-effort deadline parsed from conversation (UTC, advisory).",
        ),
        sa.Column(
            "source_kind",
            sa.String(length=20),
            nullable=False,
            server_default="conversation",
            comment="Extraction origin (v1: conversation).",
        ),
        sa.Column(
            "source_ref",
            sa.String(length=255),
            nullable=True,
            comment="Conversation thread id the loop was extracted from.",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="open",
            comment="open | closed | expired (OpenLoopStatus).",
        ),
        sa.Column(
            "closed_reason",
            sa.String(length=40),
            nullable=True,
            comment="conversational | api | expired — why the loop left OPEN.",
        ),
        sa.Column(
            "last_nudged_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last heartbeat notification that surfaced this loop (cooldown).",
        ),
        sa.Column(
            "nudge_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="How many notifications surfaced this loop.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_open_loops_user_id", "open_loops", ["user_id"])
    op.create_index(
        "ix_open_loops_user_open",
        "open_loops",
        ["user_id"],
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    """Drop the open_loops table (indexes fall with it)."""
    op.drop_index("ix_open_loops_user_open", table_name="open_loops")
    op.drop_index("ix_open_loops_user_id", table_name="open_loops")
    op.drop_table("open_loops")
