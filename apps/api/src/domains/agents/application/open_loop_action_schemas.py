"""Source correction/closure inputs, with explicit dates and sealed comparison facts."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StrictBool,
    field_validator,
    model_validator,
)

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.open_loops.management_commands import OpenLoopSnapshot, changed_open_loop
from src.domains.open_loops.schemas import CloseLoopRequest, UpdateLoopRequest


class OpenLoopChanges(UpdateLoopRequest):
    model_config = ConfigDict(frozen=True, extra="forbid")
    due_hint: AwareDatetime | None = None
    clear_due_hint: StrictBool = False

    @field_validator("subject", "due_hint", mode="before")
    @classmethod
    def refuse_ambiguous_value(cls, value: object) -> object:
        if value is None:
            raise ValueError(
                "Omit an unchanged field; clear_due_hint explicitly removes a deadline"
            )
        if not isinstance(value, str | datetime):
            raise ValueError("Use text or an explicit ISO date with a timezone")
        return value

    @model_validator(mode="after")
    def require_effect(self) -> Self:
        if self.subject is None and self.due_hint is None and not self.clear_due_hint:
            raise ValueError("Choose a wording or deadline correction")
        return self


class OpenLoopUpdateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    loop_id: UUID
    changes: OpenLoopChanges


class OpenLoopCloseRequest(CloseLoopRequest):
    model_config = ConfigDict(frozen=True, extra="forbid")
    loop_id: UUID


class OpenLoopUpdateValues(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected: OpenLoopSnapshot
    changes: OpenLoopChanges


class OpenLoopUpdatePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    open_loop: OpenLoopUpdateValues


class OpenLoopCloseValues(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected: OpenLoopSnapshot
    action: CloseLoopRequest

    @field_validator("action", mode="before")
    @classmethod
    def source_action_only(cls, value: object) -> object:
        if isinstance(value, CloseLoopRequest):
            value = value.model_dump()
        if not isinstance(value, dict) or set(value) != {"action"}:
            raise ValueError("Only the source closure action is accepted")
        return value


class OpenLoopClosePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    open_loop: OpenLoopCloseValues


def open_loop_command(
    draft: ApplicationActionDraftContent,
) -> tuple[OpenLoopSnapshot, UpdateLoopRequest | CloseLoopRequest]:
    if draft.operation_id == "open_loops.update":
        correction = OpenLoopUpdatePatch.model_validate(draft.intent).open_loop
        return correction.expected, correction.changes
    if draft.operation_id == "open_loops.close":
        closure = OpenLoopClosePatch.model_validate(draft.intent).open_loop
        return closure.expected, closure.action
    raise ValueError("Unknown commitment action")


def canonical_open_loop(draft: ApplicationActionDraftContent) -> bool:
    expected, change = open_loop_command(draft)
    return draft.before == {"open_loop": expected.model_dump(mode="json")} and draft.after == {
        "open_loop": changed_open_loop(expected, change).model_dump(mode="json")
    }
