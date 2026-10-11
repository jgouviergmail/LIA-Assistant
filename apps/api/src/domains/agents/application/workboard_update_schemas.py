"""Full source update shape plus explicit move/run controls and private source proof."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.workboard.answers import Answer
from src.domains.workboard.schemas import MoveRequest, TicketUpdate


class WorkboardMoveInput(MoveRequest):
    model_config = ConfigDict(extra="forbid", frozen=True)
    position: StrictInt = Field(ge=0)


class WorkboardUpdateInput(TicketUpdate):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ticket_id: UUID
    clear_start_at: StrictBool = False
    clear_due_at: StrictBool = False
    follow: StrictBool | None = None
    move: WorkboardMoveInput | None = None
    run_now: StrictBool = False

    @field_validator("start_at", "due_at")
    @classmethod
    def explicit_instants(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("Native dates require a timezone; legacy local dates are normalized")
        return value

    @model_validator(mode="after")
    def coherent_controls(self) -> WorkboardUpdateInput:
        if self.move is not None and self.status is not None:
            raise ValueError("Use move or status, never two destinations")
        if self.run_now and (self.move is not None or self.status not in {None, "todo"}):
            raise ValueError("Run-now requires the todo column")
        return self

    def source_changes(self) -> TicketUpdate:
        return TicketUpdate.model_validate(
            self.model_dump(exclude={"ticket_id", "move", "run_now"}, exclude_none=True)
        )


class WorkboardUpdateSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: WorkboardUpdateInput
    before: dict[str, JsonValue]
    after: dict[str, JsonValue]
    pending_preview: list[str]
    answer_note: str | None
    answer: Answer | None
    pending_before: bool
    pending_after: bool
    pending_approved: bool
    holder_name: str | None
    owner_id: UUID
    requires_peers: bool
    statuses: tuple[str, ...]
    events_before: int = Field(ge=0)
    expected_events: list[dict[str, JsonValue]]
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            "ticket_id": str(self.request.ticket_id),
            "configuration": self.request.model_dump(mode="json"),
            "ticket": self.after if after else self.before,
            "pending_preview": list(self.pending_preview),
            "answer_note": self.answer_note,
            "answer": self.answer.value if self.answer else None,
            "pending_action_present": self.pending_after if after else self.pending_before,
            "pending_action_approved": after and self.pending_approved,
            "pending_action_discarded": after and self.pending_before and not self.pending_after,
            "lia_may_run_later": after and self.after.get("assignee_kind") == "lia",
            "holder_name": self.holder_name,
            "run_requested": after and self.request.run_now,
            "update_requested": after,
        }


class WorkboardUpdatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    workboard_update: WorkboardUpdateSelection


class WorkboardUpdateField(StrEnum):
    UPDATE = "workboard_update"


def canonical_workboard_update(draft: ApplicationActionDraftContent) -> bool:
    selected = WorkboardUpdatePatch.model_validate(draft.intent).workboard_update
    return draft.before == {"workboard_update": selected.public_scope()} and draft.after == {
        "workboard_update": selected.public_scope(after=True)
    }
