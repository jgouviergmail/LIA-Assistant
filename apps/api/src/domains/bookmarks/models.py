"""One answer the person kept (ADR-282).

A bookmark is a COPY, not a pointer: the answer and the request that produced
it are stored at the click, so the bookmark survives the conversation. The
references it keeps (``message_id``, ``conversation_id``) are ``SET NULL`` on
delete — they only serve the bubble's toggle while the conversation lives.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel

#: Column comments, shared with the migration — the replay check compares them.
CONTENT_COMMENT = (
    "The answer as the assistant produced it: markdown or a lia-response HTML document."
)
REQUEST_COMMENT = (
    "The person's request that produced the answer; NULL when no visible one precedes it."
)
ANSWERED_AT_COMMENT = "When the answer was written (the message's created_at)."
MESSAGE_ID_COMMENT = "The archived message while it exists; NULL once the conversation is gone."
CONVERSATION_ID_COMMENT = "The conversation while it exists; NULL once it is gone."


class MessageBookmark(BaseModel):
    """An assistant answer the account chose to keep.

    Attributes:
        user_id: Whose bookmark. Every read filters on it.
        message_id: The archived message it was taken from, while that row
            exists. With ``user_id`` it is the identity the bubble toggles on
            (partial unique index).
        conversation_id: The conversation it was taken from, while it exists.
        content: The answer, verbatim — markdown or a ``lia-response`` HTML
            document, rendered by the same component as the bubble.
        request_content: The person's words that produced the answer, or
            ``None`` when no visible user message precedes it (a proactive
            notification).
        answered_at: When the answer was written. The tab sorts on it: a
            bookmark is dated by its answer, not by the click.
    """

    __tablename__ = "message_bookmarks"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversation_messages.id", ondelete="SET NULL"),
        nullable=True,
        comment=MESSAGE_ID_COMMENT,
    )
    conversation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        comment=CONVERSATION_ID_COMMENT,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment=CONTENT_COMMENT)
    request_content: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment=REQUEST_COMMENT
    )
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment=ANSWERED_AT_COMMENT
    )

    __table_args__ = (
        # The listing's own order: newest answer first, the primary key as the
        # tie-breaker (two answers in one millisecond otherwise repeat or
        # vanish at a page boundary).
        Index(
            "ix_message_bookmarks_user_answered",
            "user_id",
            text("answered_at DESC"),
            text("id DESC"),
        ),
        # The toggle's identity: one bookmark per message per account, and a
        # detached bookmark (message gone) is not in the way of anything.
        Index(
            "uq_message_bookmarks_user_message",
            "user_id",
            "message_id",
            unique=True,
            postgresql_where=text("message_id IS NOT NULL"),
        ),
    )
