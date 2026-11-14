"""The multipart equivalent of the chat's complete discussion-selection pair."""

from typing import Annotated
from uuid import UUID

from fastapi import Form
from fastapi.exceptions import RequestValidationError
from pydantic import Field, TypeAdapter, ValidationError

from src.core.constants import ATTACHMENTS_FILENAME_MAX_CHARS, CONVERSATION_REVISION_MAX
from src.core.conversation_selection import ConversationSelection

_FILENAME: TypeAdapter[str] = TypeAdapter(
    Annotated[str, Field(max_length=ATTACHMENTS_FILENAME_MAX_CHARS, pattern=r"^[^\x00]*$")]
)


def validate_upload_filename(filename: str) -> str:
    """Refuse an unstorable multipart filename before reading or writing its file."""
    try:
        return _FILENAME.validate_python(filename)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc


def upload_selection(
    conversation_id: Annotated[UUID | None, Form()] = None,
    conversation_revision: Annotated[int | None, Form(ge=0, le=CONVERSATION_REVISION_MAX)] = None,
) -> ConversationSelection:
    """Malformed and partial form pairs are 422, never a silent Main fallback or 500."""
    try:
        return ConversationSelection(
            conversation_id=conversation_id, conversation_revision=conversation_revision
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
