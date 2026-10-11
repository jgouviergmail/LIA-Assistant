"""Only an owned meeting identifier may be requested; delivery facts are sealed."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.infrastructure.meeting_email import MeetingEmailSnapshot


class MeetingEmailInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_id: UUID


class MeetingEmailPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_email_send: MeetingEmailSnapshot


class MeetingEmailField(StrEnum):
    SEND = "meeting_email_send"


def email_states(
    selected: MeetingEmailSnapshot,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    return {"meeting_email_send": selected.public_scope()}, {
        "meeting_email_send": {
            **selected.public_scope(),
            "send_requested": True,
            "recipient_delivery_confirmed": False,
        },
    }


def canonical_meeting_email(draft: ApplicationActionDraftContent) -> bool:
    selected = MeetingEmailPatch.model_validate(draft.intent).meeting_email_send
    before, after = email_states(selected)
    return (
        draft.operation_id == "meeting_report.email"
        and draft.before == before
        and draft.after == after
    )
