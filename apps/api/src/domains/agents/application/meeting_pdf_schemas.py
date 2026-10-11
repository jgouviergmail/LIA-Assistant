"""Whole current-minutes PDF scope with source witnesses hidden from the model."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.infrastructure.meeting_pdf import MeetingPDFSnapshot


class MeetingPDFInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_id: UUID


class MeetingPDFPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_pdf_download: MeetingPDFSnapshot


def canonical_meeting_pdf(draft: ApplicationActionDraftContent) -> bool:
    selected = MeetingPDFPatch.model_validate(draft.intent).meeting_pdf_download
    return draft.before == {"meeting_pdf_download": None} and draft.after == {
        "meeting_pdf_download": selected.public_scope()
    }
