"""Public source feedback is validated as a complete stored correction before approval."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, JsonValue, model_validator

from src.core.exceptions import ValidationError
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.journal_consolidation_schemas import JournalConsolidationScope
from src.domains.journals.portrait_feedback_configuration import portrait_feedback_entry
from src.domains.journals.schemas import JournalPortraitFeedbackRequest


class JournalFeedbackField(StrEnum):
    FEEDBACK = "journal_feedback"


class JournalFeedbackRequest(JournalPortraitFeedbackRequest):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="after")
    def require_complete_correction(self) -> JournalFeedbackRequest:
        try:
            portrait_feedback_entry(self)
        except ValidationError as exc:
            raise ValueError(
                "Provide a nonblank correction within the combined source length"
            ) from exc
        return self


class JournalFeedbackValues(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request: JournalFeedbackRequest
    expected: JournalConsolidationScope


class JournalFeedbackPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    journal_feedback: JournalFeedbackValues


def feedback_public_scope(values: JournalFeedbackValues) -> dict[str, JsonValue]:
    return {
        **values.expected.public_scope(),
        "correction": portrait_feedback_entry(values.request).model_dump(mode="json"),
    }


def canonical_journal_feedback(draft: ApplicationActionDraftContent) -> bool:
    selected = JournalFeedbackPatch.model_validate(draft.intent).journal_feedback
    public = feedback_public_scope(selected)
    return draft.before == {"journal_feedback": public} and draft.after == {
        "journal_feedback": {**public, "requested": True}
    }
