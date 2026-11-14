"""A message written while LIA works waits its turn.

Revision ID: 41dd8c9c2117
Revises: a57db671b943

An account runs one graph at a time; a message written meanwhile was refused with
HTTP 409 and lost (ADR-384). ``waiting_messages`` keeps it, one per discussion,
until the account is released: it leaves by itself after a run that ended
normally, is held after any other end, and is deleted in the transaction that
archives it. ``conversation_executions.end_state`` records how each run ended,
as its driver declared it, written by the close.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "41dd8c9c2117"
down_revision: str | Sequence[str] | None = "a57db671b943"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The chat route's bound when this revision was written (CHAT_MESSAGE_MAX_LENGTH).
_MESSAGE_MAX_LENGTH = 10_000
_RUN_ID_MAX_LENGTH = 255


def upgrade() -> None:
    """Record each run's end and create the waiting messages."""
    op.add_column(
        "conversation_executions",
        sa.Column(
            "end_state",
            sa.String(11),
            nullable=True,
            comment=(
                "How the run ended, declared by its driver; NULL until closed or if undeclared."
            ),
        ),
    )
    op.create_check_constraint(
        "conversation_execution_end",
        "conversation_executions",
        "end_state IN ('normal', 'interrupted', 'unstarted')",
    )
    op.create_check_constraint(
        "ck_execution_end_state",
        "conversation_executions",
        "end_state IS NULL OR phase = 'closed'",
    )
    op.create_table(
        "waiting_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "conversation_revision",
            sa.BigInteger(),
            nullable=False,
            comment="The discussion's generation the message was written for.",
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
            comment="The person's words, later ones added after a blank line.",
        ),
        sa.Column("status", sa.String(9), nullable=False),
        sa.Column(
            "stream_id",
            sa.String(length=_RUN_ID_MAX_LENGTH),
            nullable=True,
            comment="The invocation sending it; set only while departing.",
        ),
        sa.Column(
            "send_requested_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment=(
                "When the person asked to send it now; it then leaves first at the next release."
            ),
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            comment=(
                "Bumped on every change of the text; an edit or a claim names the one it read."
            ),
        ),
        sa.Column(
            "rendering",
            postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
            nullable=True,
            comment="The browser's display hints at the last send; never its location.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('waiting', 'held', 'departing')", name="waiting_message_status"
        ),
        sa.CheckConstraint(
            "(status = 'departing') = (stream_id IS NOT NULL)",
            name="ck_waiting_message_departure",
        ),
        sa.CheckConstraint(
            f"char_length(content) BETWEEN 1 AND {_MESSAGE_MAX_LENGTH}",
            name="ck_waiting_message_length",
        ),
        sa.CheckConstraint("version > 0", name="ck_waiting_message_version"),
        sa.CheckConstraint("conversation_revision >= 0", name="ck_waiting_message_revision"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_waiting_messages_conversation", "waiting_messages", ["conversation_id"], unique=True
    )
    op.create_index(
        "uq_waiting_messages_owner_stream",
        "waiting_messages",
        ["user_id", "stream_id"],
        unique=True,
        postgresql_where=sa.text("stream_id IS NOT NULL"),
    )
    op.create_index(
        "ix_waiting_messages_owner_created", "waiting_messages", ["user_id", "created_at"]
    )


def downgrade() -> None:
    """Drop the waiting messages (what waited is lost) and the recorded ends."""
    op.drop_index("ix_waiting_messages_owner_created", table_name="waiting_messages")
    op.drop_index("uq_waiting_messages_owner_stream", table_name="waiting_messages")
    op.drop_index("uq_waiting_messages_conversation", table_name="waiting_messages")
    op.drop_table("waiting_messages")
    op.drop_constraint("ck_execution_end_state", "conversation_executions", type_="check")
    op.drop_constraint("conversation_execution_end", "conversation_executions", type_="check")
    op.drop_column("conversation_executions", "end_state")
