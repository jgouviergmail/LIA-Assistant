"""Only the meeting id is editable; deletion never widens to derived minutes."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.infrastructure.meeting_deletions import MeetingDeletionSnapshot


class MeetingDeletionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_id: UUID


class MeetingDeletionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_delete: MeetingDeletionSnapshot


class MeetingDeletionField(StrEnum):
    DELETE = "meeting_delete"


def deletion_states(
    selected: MeetingDeletionSnapshot,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    return {"meeting_delete": selected.public_scope()}, {
        "meeting_delete": {
            "meeting_id": str(selected.meeting_id),
            "database_deleted": True,
            "files_cleanup_requested": True,
            "derived_minutes_deleted": False,
        }
    }


def canonical_meeting_deletion(draft: ApplicationActionDraftContent) -> bool:
    selected = MeetingDeletionPatch.model_validate(draft.intent).meeting_delete
    before, after = deletion_states(selected)
    return (
        draft.operation_id == "meeting.delete" and draft.before == before and draft.after == after
    )
