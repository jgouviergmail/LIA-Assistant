"""HTTP contract of the message that waits for its turn (ADR-384, ADR-385)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.core.constants import CHAT_MESSAGE_MAX_LENGTH, CONVERSATION_RUN_ID_MAX_LENGTH
from src.domains.conversations.waiting_models import WaitingMessage, WaitingStatus

#: A stream identity as the server mints it; the request only names one it was shown.
_STREAM_ID_PATTERN = r"^[0-9A-Za-z_.:-]+$"


class WaitingRendering(BaseModel):
    """The browser's display hints kept with the message; its location never is."""

    lia_gender: Literal["male", "female"] | None = Field(
        default=None, description="LIA avatar gender preference (voice selection)."
    )
    viewport: Literal["mobile", "tablet", "desktop"] | None = Field(
        default=None, description="Device viewport type when the message was written."
    )
    viewport_width: int | None = Field(
        default=None, ge=0, le=100_000, description="Screen width in pixels."
    )


class WaitingMessageRequest(BaseModel):
    """Words written while LIA works, added to the discussion's waiting message."""

    message: str = Field(
        min_length=1, max_length=CHAT_MESSAGE_MAX_LENGTH, description="The person's new words."
    )
    behind_stream_id: str | None = Field(
        default=None,
        max_length=CONVERSATION_RUN_ID_MAX_LENGTH,
        pattern=_STREAM_ID_PATTERN,
        description=(
            "The run the words were written behind; when it has already ended, its end "
            "decides whether they leave now. None: a plain send, which leaves when free."
        ),
    )
    rendering: WaitingRendering | None = Field(
        default=None, description="Display hints for the turn the message will start."
    )


class WaitingMessageEdit(BaseModel):
    """The new words of a waiting message, for the version the person edited."""

    message: str = Field(
        min_length=1, max_length=CHAT_MESSAGE_MAX_LENGTH, description="The replacing words."
    )
    version: int = Field(ge=1, description="The version the person edited.")


class WaitingMessageJoin(BaseModel):
    """Add the waiting message to the answer being written, at the version the person saw."""

    version: int = Field(ge=1, description="The version the person saw.")


class WaitingMessageResponse(BaseModel):
    """One discussion's waiting message as the person sees it, projected by ``of``."""

    conversation_id: UUID = Field(description="The discussion it was written in.")
    conversation_revision: int = Field(description="The generation it was written for.")
    content: str = Field(description="The person's words.")
    status: WaitingStatus = Field(description="waiting, held, departing or joining.")
    version: int = Field(description="The version an edit, a claim or a join names.")
    send_requested: bool = Field(description="The person asked to send it now.")
    stream_id: str | None = Field(
        description="The run sending it (departing) or about to read it (joining)."
    )
    can_join: bool = Field(
        default=False,
        description=(
            "The answer being written in this discussion takes it as a note now (ADR-385)."
        ),
    )
    created_at: datetime = Field(description="When it was first written (UTC).")
    updated_at: datetime = Field(description="When it last changed (UTC).")

    @classmethod
    def of(cls, row: WaitingMessage, *, note_stream: str | None = None) -> WaitingMessageResponse:
        """Project a row; the rendering hints stay server-side.

        Args:
            row: The waiting message.
            note_stream: The stream of the answer that takes notes in its discussion,
                read by the caller; None when none does.

        Returns:
            The projection.
        """
        return cls(
            conversation_id=row.conversation_id,
            conversation_revision=row.conversation_revision,
            content=row.content,
            status=row.status,
            version=row.version,
            send_requested=row.send_requested_at is not None,
            stream_id=row.stream_id,
            can_join=note_stream is not None
            and row.status in (WaitingStatus.WAITING, WaitingStatus.HELD),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class WaitingQueueResponse(BaseModel):
    """What became of the words just written."""

    waiting: WaitingMessageResponse | None = Field(
        description="The waiting message, or None once it entered the discussion."
    )
    departed: bool = Field(description="It left at once, the account being free.")
    stream_id: str | None = Field(default=None, description="The run sending it, if it left.")


class WaitingSendResponse(BaseModel):
    """What « Send now » set in motion."""

    departed: bool = Field(description="It left at once, the account being free.")
    stopping: bool = Field(description="The running answer of this discussion was asked to stop.")
    stream_id: str | None = Field(default=None, description="The run sending it, if it left.")
