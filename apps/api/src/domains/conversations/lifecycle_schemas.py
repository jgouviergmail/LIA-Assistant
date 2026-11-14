"""Owner-facing lifecycle requests and reconciliation results without private runtime keys."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.constants import CONVERSATION_REVISION_MAX
from src.domains.conversations.cleanup_contracts import CleanupState


class ConversationOperationRequest(BaseModel):
    """One retryable act names the exact generation the person reviewed."""

    model_config = ConfigDict(extra="forbid")

    operation_id: UUID = Field(
        description="Stable client-generated identity reused after a lost reply"
    )
    expected_revision: int = Field(
        ge=0,
        le=CONVERSATION_REVISION_MAX,
        strict=True,
        description="Generation shown when the person requested the operation",
    )


class ConversationOperationResponse(BaseModel):
    """Logical retirement is distinct from its independently recoverable cleanup."""

    operation_id: UUID = Field(description="Owner-scoped request identity for reconciliation")
    previous_message_count: int = Field(
        description="The discussion's message counter before this act"
    )
    conversation_id: UUID = Field(description="Business discussion identity")
    old_revision: int = Field(description="Retired generation")
    new_revision: int | None = Field(
        description="Current generation after reset, absent after deletion"
    )
    state: CleanupState = Field(description="Durable physical cleanup status")
    logical_applied: bool = Field(description="The logical transition has committed")
    cleanup_complete: bool = Field(description="Every physical phase explicitly succeeded")
    replayed: bool = Field(description="This response resolves an earlier accepted request")
