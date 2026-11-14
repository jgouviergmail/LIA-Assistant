"""One validated selection contract for browser and internal discussion entry points."""

from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from src.core.constants import CONVERSATION_REVISION_MAX
from src.core.i18n_api_messages import APIMessages


class ConversationSelection(BaseModel):
    """Omission names legacy Main; an explicit target includes its visible revision."""

    conversation_id: UUID | None = Field(default=None, description="Selected business discussion.")
    conversation_revision: int | None = Field(
        default=None,
        strict=True,
        ge=0,
        le=CONVERSATION_REVISION_MAX,
        description="Revision displayed when the request was prepared.",
    )

    @model_validator(mode="after")
    def require_complete_selection(self) -> Self:
        """Refuse a partial selection instead of silently redirecting it to Main."""
        if (self.conversation_id is None) != (self.conversation_revision is None):
            raise ValueError(APIMessages.conversation_selection_incomplete())
        return self
