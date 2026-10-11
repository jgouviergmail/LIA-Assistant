"""A deletion names the owned source subtree, never a free predicate."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent


class WorkboardDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ticket_id: UUID


class WorkboardDeleteTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ticket_id: UUID
    title: str
    status: str
    running: bool
    has_pending_action: bool


class WorkboardDeleteSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: WorkboardDeleteInput
    items: list[WorkboardDeleteTarget] = Field(min_length=1)
    comments: int = Field(ge=0)
    events: int = Field(ge=0)
    owned_count: int = Field(ge=1)
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            "ticket_id": str(self.request.ticket_id),
            "items": [item.model_dump(mode="json") for item in self.items],
            "tickets": len(self.items),
            "comments": self.comments,
            "events": self.events,
            "active_runs": sum(item.running for item in self.items),
            "pending_actions": sum(item.has_pending_action for item in self.items),
            "deletion_requested": after,
        }


class WorkboardDeletePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    workboard_delete: WorkboardDeleteSelection


class WorkboardDeleteField(StrEnum):
    DELETE = "workboard_delete"


def canonical_workboard_delete(draft: ApplicationActionDraftContent) -> bool:
    selected = WorkboardDeletePatch.model_validate(draft.intent).workboard_delete
    return draft.before == {"workboard_delete": selected.public_scope()} and draft.after == {
        "workboard_delete": selected.public_scope(after=True)
    }
