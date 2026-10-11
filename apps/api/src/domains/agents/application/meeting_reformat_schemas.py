"""Strict original reformat input and sealed complete source/destination scope."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, field_validator

from src.core.meeting_reformat import MeetingReformatRequest
from src.core.meeting_templates import canonical_template_reference
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.infrastructure.meeting_reformat import MeetingReformatSnapshot


class MeetingReformatInput(MeetingReformatRequest):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_id: UUID

    @field_validator("template_ref")
    @classmethod
    def canonical_reference(cls, value: str) -> str:
        return canonical_template_reference(value) or value


class MeetingReformatPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_reformat: MeetingReformatSnapshot


class MeetingReformatField(StrEnum):
    REFORMAT = "meeting_reformat"


def reformat_states(
    selected: MeetingReformatSnapshot,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    return {"meeting_reformat": selected.public_scope()}, {
        "meeting_reformat": {
            "meeting_id": str(selected.source.meeting_id),
            "destination_id": str(selected.destination_id),
            "mode": selected.request.mode,
            "preserve_source_report": selected.request.mode == "new",
            "processing_completed": False,
            "indexing_completed": False,
        }
    }


def canonical_meeting_reformat(draft: ApplicationActionDraftContent) -> bool:
    selected = MeetingReformatPatch.model_validate(draft.intent).meeting_reformat
    before, after = reformat_states(selected)
    return (
        draft.operation_id == "meeting_report.reformat"
        and draft.before == before
        and draft.after == after
    )
