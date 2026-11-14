"""A note joins the answer being written.

Revision ID: a696c8a365f2
Revises: d6a3f0c2b8e1

A message written while LIA works can join the answer in progress instead of waiting
for the next turn (ADR-385). ``conversation_executions.accepts_notes`` says whether
the running invocation takes notes now (a ReAct loop a person waits for, between its
first model call and its exit); only a running invocation may. A waiting message that
joins becomes ``joining`` and carries the invocation's stream, like a departing one.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a696c8a365f2"
down_revision: str | Sequence[str] | None = "d6a3f0c2b8e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Let a running invocation take notes, and a waiting message join it."""
    op.add_column(
        "conversation_executions",
        sa.Column(
            "accepts_notes",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment=(
                "The answer being written takes the person's notes now: a ReAct loop a person "
                "waits for, between its first model call and its exit (ADR-385)."
            ),
        ),
    )
    op.create_check_constraint(
        "ck_execution_notes_running",
        "conversation_executions",
        "NOT accepts_notes OR phase = 'running'",
    )
    op.drop_constraint("waiting_message_status", "waiting_messages", type_="check")
    op.create_check_constraint(
        "waiting_message_status",
        "waiting_messages",
        "status IN ('waiting', 'held', 'departing', 'joining')",
    )
    op.drop_constraint("ck_waiting_message_departure", "waiting_messages", type_="check")
    op.create_check_constraint(
        "ck_waiting_message_departure",
        "waiting_messages",
        "(status IN ('departing', 'joining')) = (stream_id IS NOT NULL)",
    )
    op.alter_column(
        "waiting_messages",
        "stream_id",
        comment="The invocation sending it or reading it; set only while departing or joining.",
        existing_type=sa.String(length=255),
        existing_nullable=True,
    )


def downgrade() -> None:
    """A note nobody read waits again; the invocations no longer take notes."""
    op.execute(
        "UPDATE waiting_messages SET status = 'waiting', stream_id = NULL "
        "WHERE status = 'joining'"
    )
    op.alter_column(
        "waiting_messages",
        "stream_id",
        comment="The invocation sending it; set only while departing.",
        existing_type=sa.String(length=255),
        existing_nullable=True,
    )
    op.drop_constraint("ck_waiting_message_departure", "waiting_messages", type_="check")
    op.create_check_constraint(
        "ck_waiting_message_departure",
        "waiting_messages",
        "(status = 'departing') = (stream_id IS NOT NULL)",
    )
    op.drop_constraint("waiting_message_status", "waiting_messages", type_="check")
    op.create_check_constraint(
        "waiting_message_status",
        "waiting_messages",
        "status IN ('waiting', 'held', 'departing')",
    )
    op.drop_constraint("ck_execution_notes_running", "conversation_executions", type_="check")
    op.drop_column("conversation_executions", "accepts_notes")
