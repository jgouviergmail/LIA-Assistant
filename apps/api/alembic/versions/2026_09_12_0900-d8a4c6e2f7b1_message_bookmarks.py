"""The answers a person keeps out of their conversations (ADR-282).

A bookmark is a COPY, not a pointer: the answer and the request that produced
it are stored at the click, so deleting the conversation leaves the bookmark
whole. The two references it keeps are ``SET NULL`` — they only serve the
bubble's toggle while the conversation lives.

Two indexes: the listing's own order (newest answer first, the primary key as
the tie-breaker) and the toggle's identity, a PARTIAL unique index so a
detached bookmark (message gone) is in the way of nothing.

Revision ID: d8a4c6e2f7b1
Revises: c7e3b2d5f1a8
Create Date: 2026-09-12 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d8a4c6e2f7b1"
down_revision: str | None = "c7e3b2d5f1a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONTENT_COMMENT = (
    "The answer as the assistant produced it: markdown or a lia-response HTML document."
)
_REQUEST_COMMENT = (
    "The person's request that produced the answer; NULL when no visible one precedes it."
)
_ANSWERED_AT_COMMENT = "When the answer was written (the message's created_at)."
_MESSAGE_ID_COMMENT = "The archived message while it exists; NULL once the conversation is gone."
_CONVERSATION_ID_COMMENT = "The conversation while it exists; NULL once it is gone."


def upgrade() -> None:
    """Create the table, its listing index and its toggle identity."""
    op.create_table(
        "message_bookmarks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversation_messages.id", ondelete="SET NULL"),
            nullable=True,
            comment=_MESSAGE_ID_COMMENT,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
            comment=_CONVERSATION_ID_COMMENT,
        ),
        sa.Column("content", sa.Text(), nullable=False, comment=_CONTENT_COMMENT),
        sa.Column("request_content", sa.Text(), nullable=True, comment=_REQUEST_COMMENT),
        sa.Column(
            "answered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment=_ANSWERED_AT_COMMENT,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_message_bookmarks_user_answered",
        "message_bookmarks",
        ["user_id", sa.text("answered_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "uq_message_bookmarks_user_message",
        "message_bookmarks",
        ["user_id", "message_id"],
        unique=True,
        postgresql_where=sa.text("message_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop the table. A bookmark is the person's own copy; downgrading loses
    it, which is why this migration is not one to roll back lightly."""
    op.drop_index("uq_message_bookmarks_user_message", table_name="message_bookmarks")
    op.drop_index("ix_message_bookmarks_user_answered", table_name="message_bookmarks")
    op.drop_table("message_bookmarks")
