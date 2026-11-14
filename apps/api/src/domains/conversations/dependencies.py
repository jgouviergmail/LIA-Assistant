"""Shared HTTP selection for history, execution status and chat controls."""

from typing import Annotated
from uuid import UUID

from fastapi import Query
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from src.core.constants import CONVERSATION_REVISION_MAX
from src.core.conversation_selection import ConversationSelection


def selected_conversation(
    conversation_id: Annotated[UUID | None, Query()] = None,
    conversation_revision: Annotated[int | None, Query(ge=0, le=CONVERSATION_REVISION_MAX)] = None,
) -> ConversationSelection:
    """Parse query strings and enforce the same complete pair as the JSON body."""
    try:
        return ConversationSelection(
            conversation_id=conversation_id,
            conversation_revision=conversation_revision,
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
