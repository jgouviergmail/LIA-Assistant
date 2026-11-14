"""Bounded requests and owner-visible metadata for the discussion catalogue."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from src.core.constants import (
    CONVERSATION_REVISION_MAX,
    CONVERSATION_TITLE_MAX_LENGTH,
    CONVERSATION_TITLE_PATTERN,
    CONVERSATION_TITLE_WHITESPACE,
)
from src.core.i18n_api_messages import APIMessages
from src.core.text_clip import has_visible_text
from src.domains.conversations.schemas import ConversationResponse


class _TitleGrammar(BaseModel):
    """One title grammar for creation and renaming: what a SENT title must be."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", mode="before", check_fields=False)
    @classmethod
    def normalize_title(cls, value: object, info: ValidationInfo) -> object:
        """Apply the published length bound to the trimmed value, never coerce types."""
        return value.strip(CONVERSATION_TITLE_WHITESPACE) if isinstance(value, str) else value

    @field_validator("title", check_fields=False)
    @classmethod
    def require_visible_title(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Reject an unreadable title without altering international writing."""
        if value is not None and not has_visible_text(value):
            raise ValueError(APIMessages.conversation_title_required())
        return value


class ConversationTitleInput(_TitleGrammar):
    """A title its owner typed."""

    title: str = Field(
        min_length=1,
        max_length=CONVERSATION_TITLE_MAX_LENGTH,
        pattern=CONVERSATION_TITLE_PATTERN,
        description="Required discussion title.",
    )


class ConversationCreateRequest(_TitleGrammar):
    """One creation attempt, retryable without creating a second annex.

    The title is optional (ADR-378 amendment 2026-11-12): omitted or null, the
    discussion takes its title from the first message its owner writes in it.
    A title that IS sent is held to the grammar — a blank one is refused, never
    read as a request for an automatic title.
    """

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=CONVERSATION_TITLE_MAX_LENGTH,
        pattern=CONVERSATION_TITLE_PATTERN,
        description=(
            "Discussion title. Omitted or null: the discussion takes its title "
            "from the first message written in it."
        ),
    )
    request_id: UUID = Field(
        description="Stable client attempt UUID, reused only for the same creation."
    )


class ConversationRenameRequest(ConversationTitleInput):
    """Change the title of the exact annex the person reviewed."""

    expected_title: str = Field(
        min_length=1,
        max_length=CONVERSATION_TITLE_MAX_LENGTH,
        pattern=CONVERSATION_TITLE_PATTERN,
        description="Stored title that was shown when editing began",
    )
    expected_revision: int = Field(
        ge=0,
        le=CONVERSATION_REVISION_MAX,
        strict=True,
        description="Conversation generation that was shown when editing began",
    )


class ConversationCreateResult(BaseModel):
    """Return the original result identity on an accepted replay."""

    conversation: ConversationResponse = Field(
        description="Created or previously created discussion."
    )
    replayed: bool = Field(description="Whether the attempt had already committed.")


class ConversationPageResponse(BaseModel):
    """Exact owner-scoped total and one bounded metadata page."""

    items: list[ConversationResponse] = Field(description="Discussion metadata, with Main first.")
    total_count: int = Field(
        ge=0, description="Exact count of all active discussions owned by the account."
    )
    limit: int = Field(ge=1, description="Effective page size.")
    offset: int = Field(ge=0, description="Number of rows preceding this page.")
