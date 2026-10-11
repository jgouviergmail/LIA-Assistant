"""Only the meeting id is editable; the entire original job source is sealed."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.infrastructure.meeting_retry import MeetingRetrySnapshot


class MeetingRetryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_id: UUID


class MeetingRetryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_retry: MeetingRetrySnapshot


class MeetingRetryField(StrEnum):
    RETRY = "meeting_retry"


def retry_states(
    selected: MeetingRetrySnapshot,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    return {"meeting_retry": selected.public_scope()}, {
        "meeting_retry": {
            "meeting_id": str(selected.meeting_id),
            "retry_budget_reset": True,
            "processing_completed": False,
            "original_workflow": True,
        }
    }


def canonical_meeting_retry(draft: ApplicationActionDraftContent) -> bool:
    selected = MeetingRetryPatch.model_validate(draft.intent).meeting_retry
    before, after = retry_states(selected)
    return draft.operation_id == "meeting.retry" and draft.before == before and draft.after == after
