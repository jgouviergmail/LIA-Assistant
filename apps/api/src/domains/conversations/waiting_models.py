"""A message written while LIA works, kept by the server until its turn (ADR-384)."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.constants import CHAT_MESSAGE_MAX_LENGTH, CONVERSATION_RUN_ID_MAX_LENGTH
from src.infrastructure.database.models import BaseModel


class WaitingStatus(StrEnum):
    """Where a waiting message stands.

    ``WAITING`` leaves by itself after a normal end, ``HELD`` only on the person's
    click, ``DEPARTING`` is claimed by the run that is sending it, ``JOINING`` is
    addressed to the answer being written and read by its loop at its next model
    call (ADR-385).
    """

    WAITING = "waiting"
    HELD = "held"
    DEPARTING = "departing"
    JOINING = "joining"


class WaitingMessage(BaseModel):
    """One per discussion; a departing or joining one carries its run's stream.

    A departing message takes no more words; a joining one still does, until the
    loop reads it (ADR-385).

    The text is the person's own words, stored like an archived message; it never
    appears in a log. The rendering hints are the browser's non-personal display facts
    (avatar voice, viewport): its location is never kept here.
    """

    __tablename__ = "waiting_messages"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    conversation_revision: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="The discussion's generation the message was written for.",
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="The person's words, later ones added after a blank line."
    )
    status: Mapped[WaitingStatus] = mapped_column(
        SAEnum(
            WaitingStatus,
            name="waiting_message_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [value.value for value in values],
            validate_strings=True,
        ),
        nullable=False,
        default=WaitingStatus.WAITING,
    )
    stream_id: Mapped[str | None] = mapped_column(
        String(CONVERSATION_RUN_ID_MAX_LENGTH),
        nullable=True,
        comment="The invocation sending it or reading it; set only while departing or joining.",
    )
    send_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the person asked to send it now; it then leaves first at the next release.",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Bumped on every change of the text; an edit or a claim names the one it read.",
    )
    rendering: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
        comment="The browser's display hints at the last send; never its location.",
    )

    __table_args__ = (
        Index("uq_waiting_messages_conversation", "conversation_id", unique=True),
        Index(
            "uq_waiting_messages_owner_stream",
            "user_id",
            "stream_id",
            unique=True,
            postgresql_where=text("stream_id IS NOT NULL"),
        ),
        Index("ix_waiting_messages_owner_created", "user_id", "created_at"),
        CheckConstraint(
            "(status IN ('departing', 'joining')) = (stream_id IS NOT NULL)",
            name="ck_waiting_message_departure",
        ),
        CheckConstraint(
            f"char_length(content) BETWEEN 1 AND {CHAT_MESSAGE_MAX_LENGTH}",
            name="ck_waiting_message_length",
        ),
        CheckConstraint("version > 0", name="ck_waiting_message_version"),
        CheckConstraint("conversation_revision >= 0", name="ck_waiting_message_revision"),
    )
