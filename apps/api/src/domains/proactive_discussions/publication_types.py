"""Validated publication input and durable idempotency receipt."""

from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, StrictBool, model_validator

from src.core.constants import DISCUSSION_OPENING_MAX_CHARS, DISCUSSION_OPENING_PROOFS_MAX
from src.domains.proactive_discussions.context_store.schemas import ContextEvidenceLink
from src.domains.proactive_discussions.schemas import EngageDecision
from src.domains.shared.discussion_sources import DiscussionValue


class OpeningDraft(DiscussionValue):
    """A validated opening ready to publish: its decision, wording, fingerprint and proofs."""

    decision: EngageDecision
    text: Annotated[str, Field(min_length=1, max_length=DISCUSSION_OPENING_MAX_CHARS)]
    fingerprint: Annotated[str, Field(min_length=1, max_length=128)]
    sensitive_context: StrictBool = Field(
        default=False, description="Deliver privately: push masked, no external channel."
    )
    sms_context: StrictBool = Field(
        default=False,
        description="The run read an SMS: private delivery and no later decision window.",
    )
    proofs: Annotated[
        tuple[ContextEvidenceLink, ...], Field(max_length=DISCUSSION_OPENING_PROOFS_MAX)
    ] = ()

    @model_validator(mode="after")
    def sms_is_private(self) -> Self:
        """Refuse an SMS-informed opening that is not private (ADR-357)."""
        if self.sms_context and not self.sensitive_context:
            raise ValueError("an SMS-informed opening is private (ADR-357)")
        return self


class PublicationReceipt(DiscussionValue):
    """What a publication created, or found already created for the same run."""

    opening_id: UUID
    message_id: UUID
    conversation_id: UUID
    created: StrictBool
