"""Wire shapes of the bookmarks API (ADR-282).

Mirrored by ``apps/web/src/types/bookmarks.ts`` — a test pins the two, because
a field spelled two ways is how a card behaves differently live and after a
reload.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BookmarkKeepRequest(BaseModel):
    """What the bubble sends: the archived message it stands for."""

    message_id: uuid.UUID = Field(description="The archived assistant message to keep.")


class BookmarkResponse(BaseModel):
    """One kept answer, as the tab and the bubble read it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Bookmark id.")
    message_id: uuid.UUID | None = Field(
        default=None,
        description="The archived message while it exists; None once the conversation is gone.",
    )
    conversation_id: uuid.UUID | None = Field(
        default=None, description="The conversation while it exists; None once it is gone."
    )
    content: str = Field(description="The answer, verbatim: markdown or a lia-response document.")
    request_content: str | None = Field(
        default=None,
        description="The person's request that produced the answer; None when none did.",
    )
    answered_at: datetime = Field(description="When the answer was written (UTC).")
    created_at: datetime = Field(description="When the answer was kept (UTC).")


class BookmarkListResponse(BaseModel):
    """One page of bookmarks, its exact total, and the bounds it obeys."""

    items: list[BookmarkResponse]
    total: int = Field(description="EXACT count over the whole filtered set (ADR-185).")
    limit: int = Field(description="Page size applied.")
    offset: int = Field(description="Page start applied.")
    max_limit: int = Field(
        description="Largest page this API serves — published because it is enforced (ADR-184).",
    )
    max_per_user: int = Field(
        description="How many bookmarks the account may keep — published because it is enforced.",
    )


class BookmarkStateResponse(BaseModel):
    """What every bubble needs to draw its toggle."""

    message_ids: dict[uuid.UUID, uuid.UUID] = Field(
        description="message_id → bookmark_id, for every bookmark still attached to a message.",
    )
