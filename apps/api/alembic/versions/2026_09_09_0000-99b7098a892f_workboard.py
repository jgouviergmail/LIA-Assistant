"""Workboard (ADR-276): tickets, comments and an append-only event log.

One ticket row shared by its owner and its assignee — the board of user U is
« owner = U or assignee = U », so there are no per-board copies and the two
sides can never disagree about a ticket's state.

Two shapes carry a decision:

- ``assignee_user_id`` is **nullable and SET NULL**: NULL means « the owner
  holds it ». Four paths hard-delete a ``users`` row and only one of them runs
  the account purge, so CASCADE would destroy the OWNER's ticket when their
  peer leaves and RESTRICT would block the three paths that never release.
  SET NULL hands the ticket back on every path. The purge ALSO releases
  explicitly, because account deletion scrubs the users row rather than
  deleting it and no FK action fires there.
- There is **no ``peer_connection_id``**. Storing the connection that
  authorised a peer assignment needed a CHECK tying two columns, and deleting
  the peer's account fires two independent FK actions on this row in an order
  the standard does not fix — proved on real PostgreSQL 2026-09-09, the CHECK
  rejects whichever intermediate state comes first, and ``CHECK`` cannot be
  ``DEFERRABLE``. The pair ``(owner, assignee)`` IS the connection anyway:
  ``peer_connections`` holds one row per pair for life.

The partial index serves the sweep's eligibility scan (lot 2): most of a board
is not waiting for LIA, and the index must not carry it.

Revision ID: 99b7098a892f
Revises: 00fae77284aa
Create Date: 2026-09-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "99b7098a892f"
down_revision: str | None = "00fae77284aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the three workboard tables with their indexes."""
    op.create_table(
        "workboard_tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="The board it was created on. Dies with the account.",
        ),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Parent ticket (ONE level — a child never has children).",
        ),
        sa.Column("title", sa.Text(), nullable=False, comment="What the ticket is."),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
            comment="The brief LIA runs when assigned; the owner's words.",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            comment="idea | todo | in_progress | waiting | confirming | validating | done",
        ),
        sa.Column(
            "priority",
            sa.String(length=10),
            nullable=False,
            comment="low | medium | high | urgent",
        ),
        sa.Column(
            "start_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC instant work may start.",
        ),
        sa.Column(
            "due_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC instant it is due.",
        ),
        sa.Column(
            "assignee_kind",
            sa.String(length=10),
            nullable=False,
            comment="human | lia — whose hands, or whose assistant.",
        ),
        sa.Column(
            "assignee_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Account holding it; NULL means the owner does. SET NULL releases it.",
        ),
        sa.Column(
            "position",
            sa.Integer(),
            nullable=False,
            comment="Order inside a column, on the OWNER's board.",
        ),
        sa.Column(
            "follow_owner",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Owner wants chat notifications about this ticket.",
        ),
        sa.Column(
            "follow_assignee",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Assignee wants chat notifications; reset on reassignment.",
        ),
        sa.Column(
            "created_by",
            sa.String(length=10),
            nullable=False,
            comment="user | lia | peer — who created it.",
        ),
        sa.Column(
            "status_changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When status last changed (closed-hide filter, waiting-too-long nudge).",
        ),
        sa.Column(
            "run_not_before",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Quota back-off; set by the sweep only.",
        ),
        sa.Column(
            "run_claimed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="A run holds this ticket since.",
        ),
        sa.Column(
            "run_attempts",
            sa.Integer(),
            nullable=False,
            comment="Attempts of the CURRENT run.",
        ),
        sa.Column(
            "run_count",
            sa.Integer(),
            nullable=False,
            comment="Runs in the ticket's life (bounds the hidden transcripts).",
        ),
        sa.Column(
            "last_run_id",
            sa.String(length=100),
            nullable=True,
            comment="run_id of the last run (registers join key).",
        ),
        sa.Column(
            "last_run_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC instant the last run ended.",
        ),
        sa.Column(
            "last_run_outcome",
            sa.String(length=20),
            nullable=True,
            comment="success | waiting | confirming | failed | skipped_quota | skipped_busy",
        ),
        sa.Column(
            "last_run_error",
            sa.Text(),
            nullable=True,
            comment="Typed code + bounded message; never a traceback.",
        ),
        sa.Column(
            "last_run_tokens_in",
            sa.Integer(),
            nullable=True,
            comment="Prompt tokens the last run spent.",
        ),
        sa.Column(
            "last_run_tokens_out",
            sa.Integer(),
            nullable=True,
            comment="Completion tokens the last run spent.",
        ),
        sa.Column(
            "last_run_cost_eur",
            sa.Numeric(precision=10, scale=6),
            nullable=True,
            comment="Cost of the last run, snapshotted from token_usage_logs.",
        ),
        sa.Column(
            "last_nudged_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last heartbeat notification that surfaced this ticket (cooldown).",
        ),
        sa.Column(
            "nudge_count",
            sa.Integer(),
            nullable=False,
            comment="How many notifications surfaced this ticket.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignee_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_id"], ["workboard_tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workboard_tickets_owner_user_id", "workboard_tickets", ["owner_user_id"], unique=False
    )
    op.create_index(
        "ix_workboard_tickets_assignee_user_id",
        "workboard_tickets",
        ["assignee_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_workboard_tickets_parent_id", "workboard_tickets", ["parent_id"], unique=False
    )
    op.create_index(
        "ix_workboard_tickets_owner_status",
        "workboard_tickets",
        ["owner_user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_workboard_tickets_assignee_status",
        "workboard_tickets",
        ["assignee_user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_workboard_tickets_lia_todo",
        "workboard_tickets",
        ["start_at"],
        unique=False,
        postgresql_where=sa.text(
            "assignee_kind = 'lia' AND status = 'todo' AND run_claimed_at IS NULL"
        ),
    )

    op.create_table(
        "workboard_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="The ticket this comment belongs to.",
        ),
        sa.Column("author_kind", sa.String(length=10), nullable=False, comment="user | lia | peer"),
        sa.Column(
            "author_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Who wrote it; NULL once that account is gone.",
        ),
        sa.Column("body", sa.Text(), nullable=False, comment="Plain text."),
        sa.Column(
            "run_id",
            sa.String(length=100),
            nullable=True,
            comment="The run that wrote it, when LIA did.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["workboard_tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workboard_comments_ticket_id", "workboard_comments", ["ticket_id"], unique=False
    )

    op.create_table(
        "workboard_ticket_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="The ticket this event belongs to.",
        ),
        sa.Column("actor_kind", sa.String(length=10), nullable=False, comment="user | lia | peer"),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Who acted; NULL once that account is gone.",
        ),
        sa.Column(
            "kind",
            sa.String(length=20),
            nullable=False,
            comment="created | status_changed | assigned | priority_changed | dates_changed "
            "| run_started | run_finished | follow_changed",
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Bounded {from, to} facts; never free text.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When it happened (UTC).",
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["workboard_tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workboard_ticket_events_ticket_id",
        "workboard_ticket_events",
        ["ticket_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the three tables, children first."""
    op.drop_index("ix_workboard_ticket_events_ticket_id", table_name="workboard_ticket_events")
    op.drop_table("workboard_ticket_events")
    op.drop_index("ix_workboard_comments_ticket_id", table_name="workboard_comments")
    op.drop_table("workboard_comments")
    for index_name in (
        "ix_workboard_tickets_lia_todo",
        "ix_workboard_tickets_assignee_status",
        "ix_workboard_tickets_owner_status",
        "ix_workboard_tickets_parent_id",
        "ix_workboard_tickets_assignee_user_id",
        "ix_workboard_tickets_owner_user_id",
    ):
        op.drop_index(index_name, table_name="workboard_tickets")
    op.drop_table("workboard_tickets")
