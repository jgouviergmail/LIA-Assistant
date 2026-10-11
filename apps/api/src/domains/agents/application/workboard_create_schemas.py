"""The creation payload inherits the UI source and pins its prerequisites privately."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, field_validator

from src.domains.workboard.schemas import TicketCreate


class WorkboardCreateInput(TicketCreate):
    model_config = ConfigDict(extra="forbid", frozen=True)
    follow: StrictBool = False

    @field_validator("start_at", "due_at")
    @classmethod
    def dates_are_explicit_instants(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError(
                "Native dates require an ISO instant with timezone; legacy local dates are normalized"
            )
        return value


class WorkboardCreateSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: WorkboardCreateInput
    assignee_kind: str
    holder_id: UUID | None
    holder_name: str | None
    parent_title: str | None
    owned_count: int = Field(ge=0)
    max_tickets: int = Field(ge=1)
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            "configuration": self.request.model_dump(mode="json"),
            "assignee_kind": self.assignee_kind,
            "holder_id": str(self.holder_id) if self.holder_id else None,
            "holder_name": self.holder_name,
            "parent_title": self.parent_title,
            "owned_count": self.owned_count,
            "max_tickets": self.max_tickets,
            "creation_requested": after,
            "lia_may_run_later": self.assignee_kind == "lia",
        }


class WorkboardCreatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    workboard_create: WorkboardCreateSelection


class WorkboardCreateField(StrEnum):
    CREATE = "workboard_create"
