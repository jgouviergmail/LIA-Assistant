"""Bounded, generation-bound history positions; no runtime authority leaves the server."""

import base64
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from src.core.constants import CONVERSATION_HISTORY_CURSOR_MAX_LENGTH, CONVERSATION_REVISION_MAX
from src.core.conversation_target import ConversationRef
from src.core.exceptions import raise_invalid_input
from src.core.i18n_api_messages import APIMessages
from src.infrastructure.database.keyset import Keyset


class HistoryCursor(BaseModel):
    """A total order and the public generation to which it belongs."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Literal[1] = Field(description="Cursor wire version.")
    conversation_id: UUID = Field(description="Owned business discussion.")
    conversation_revision: int = Field(
        ge=0, le=CONVERSATION_REVISION_MAX, description="Displayed generation."
    )
    at: AwareDatetime = Field(description="UTC instant of the last served message.")
    message_id: UUID = Field(description="Primary key breaking timestamp ties.")

    @field_validator("version", mode="before")
    @classmethod
    def _integer_version(cls, value: object, info: ValidationInfo) -> int:
        """A JSON boolean is not an integer version, despite Python's equality."""
        if type(value) is not int:
            raise ValueError(f"{info.field_name} must be an integer")
        return value


class SearchCursor(BaseModel):
    """The last message a search across discussions served: no discussion, no generation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Literal[1] = Field(description="Cursor wire version.")
    at: AwareDatetime = Field(description="UTC instant of the last served message.")
    message_id: UUID = Field(description="Primary key breaking timestamp ties.")

    @field_validator("version", mode="before")
    @classmethod
    def _integer_version(cls, value: object, info: ValidationInfo) -> int:
        """A JSON boolean is not an integer version, despite Python's equality."""
        if type(value) is not int:
            raise ValueError(f"{info.field_name} must be an integer")
        return value


def _opaque(value: BaseModel) -> str:
    return base64.urlsafe_b64encode(value.model_dump_json().encode()).decode().rstrip("=")


def _decoded(cursor: str) -> bytes:
    """The JSON a cursor carries; ``ValueError`` when it is no cursor of ours."""
    if not cursor or len(cursor) > CONVERSATION_HISTORY_CURSOR_MAX_LENGTH:
        raise ValueError("cursor")
    return base64.b64decode(
        (cursor + "=" * (-len(cursor) % 4)).encode("ascii"), altchars=b"-_", validate=True
    )


def encode_history_cursor(target: ConversationRef, at: datetime, message_id: UUID) -> str:
    """Encode only public selection coordinates and the last displayed position."""
    value = HistoryCursor(
        version=1,
        conversation_id=target.id,
        conversation_revision=target.revision,
        at=at,
        message_id=message_id,
    )
    return _opaque(value)


def encode_search_cursor(at: datetime, message_id: UUID) -> str:
    """Encode where a search across discussions resumes: the last message it served."""
    return _opaque(SearchCursor(version=1, at=at, message_id=message_id))


def search_position(cursor: str | None) -> Keyset | None:
    """Validate a search's position, refusing a damaged one or another reader's.

    Args:
        cursor: The opaque ``next_cursor`` of the previous page, or None.

    Returns:
        The shared database keyset, or None for the newest page.
    """
    if cursor is None:
        return None
    try:
        value = SearchCursor.model_validate_json(_decoded(cursor))
    except ValueError:
        raise_invalid_input(APIMessages.conversation_history_cursor_invalid())
    return Keyset(at=value.at, id=value.message_id)


def history_position(
    target: ConversationRef, *, cursor: str | None, before: datetime | None
) -> Keyset | None:
    """Validate one paging mode, rejecting damaged or cross-generation cursors.

    Args:
        target: The already authenticated, locked history generation.
        cursor: New composite cursor, opaque to the browser.
        before: Legacy timestamp-only cut; mutually exclusive with cursor.

    Returns:
        The shared database keyset, or None for the newest page.
    """
    if cursor is None:
        return Keyset(at=before) if before is not None else None
    try:
        if before is not None:
            raise ValueError("cursor")
        value = HistoryCursor.model_validate_json(_decoded(cursor))
        if (value.conversation_id, value.conversation_revision) != (target.id, target.revision):
            raise ValueError("cursor")
    except ValueError:
        raise_invalid_input(APIMessages.conversation_history_cursor_invalid())
    return Keyset(at=value.at, id=value.message_id)
