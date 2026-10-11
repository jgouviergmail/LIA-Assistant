"""Exact owned transcript deletion; private witnesses stay outside approval text."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.infrastructure.meeting_transcripts import MeetingTranscriptState


class TranscriptDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_id: UUID


class TranscriptDeleteSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: TranscriptDeleteInput
    expected: MeetingTranscriptState


class TranscriptDeletePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_transcript_delete: TranscriptDeleteSelection


class TranscriptActionField(StrEnum):
    DELETE = "meeting_transcript_delete"


def transcript_deletion_states(
    selected: TranscriptDeleteSelection,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    return {"meeting_transcript_delete": selected.expected.public_values()}, {
        "meeting_transcript_delete": {
            "meeting_id": str(selected.request.meeting_id),
            "title": selected.expected.title,
            "has_transcript": False,
            "deleted": True,
            "minutes_preserved": True,
        }
    }


def canonical_transcript_deletion(draft: ApplicationActionDraftContent) -> bool:
    selected = TranscriptDeletePatch.model_validate(draft.intent).meeting_transcript_delete
    before, after = transcript_deletion_states(selected)
    return (
        selected.request.meeting_id == selected.expected.meeting_id
        and draft.before == before
        and draft.after == after
    )
