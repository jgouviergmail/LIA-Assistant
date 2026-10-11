"""Only an owned meeting id is editable; the complete rebuild source is sealed."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.infrastructure.meeting_regeneration import MeetingRegenerationSnapshot


class MeetingRegenerationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_id: UUID


class MeetingRegenerationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_regeneration: MeetingRegenerationSnapshot


class MeetingRegenerationField(StrEnum):
    REGENERATE = "meeting_regeneration"


def regeneration_states(
    selected: MeetingRegenerationSnapshot,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    return {"meeting_regeneration": selected.public_scope()}, {
        "meeting_regeneration": {
            "meeting_id": str(selected.meeting_id),
            "replace_entire_current_report": True,
            "processing_completed": False,
            "indexing_completed": False,
        }
    }


def canonical_meeting_regeneration(draft: ApplicationActionDraftContent) -> bool:
    selected = MeetingRegenerationPatch.model_validate(draft.intent).meeting_regeneration
    before, after = regeneration_states(selected)
    return (
        draft.operation_id == "meeting_report.regenerate"
        and draft.before == before
        and draft.after == after
    )
