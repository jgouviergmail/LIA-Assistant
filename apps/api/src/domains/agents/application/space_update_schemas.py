"""One exact owned source space and sparse metadata/desired activation under human approval."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, model_validator

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.rag_spaces.schemas import RAGSpaceUpdate


class SpaceUpdateInput(RAGSpaceUpdate):
    model_config = ConfigDict(extra="forbid", frozen=True)
    space_id: UUID
    is_active: StrictBool | None = Field(
        default=None, description="Desired source activation, not a toggle"
    )

    @model_validator(mode="after")
    def requires_a_source_change(self) -> SpaceUpdateInput:
        if self.name is None and self.description is None and self.is_active is None:
            raise ValueError(
                "Provide name, description (empty clears), or desired activation; null means omitted"
            )
        return self


class SpaceUpdateTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)
    id: UUID
    name: str
    description: str | None
    is_active: bool
    kind: str | None


class SpaceUpdateSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: SpaceUpdateInput
    expected: SpaceUpdateTarget
    proposed: SpaceUpdateTarget
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            "space": (self.proposed if after else self.expected).model_dump(mode="json"),
            "update_requested": after,
        }


class SpaceUpdatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    space_update: SpaceUpdateSelection


class SpaceUpdateField(StrEnum):
    UPDATE = "space_update"


def canonical_space_update(draft: ApplicationActionDraftContent) -> bool:
    selected = SpaceUpdatePatch.model_validate(draft.intent).space_update
    return draft.before == {"space_update": selected.public_scope()} and draft.after == {
        "space_update": selected.public_scope(after=True)
    }
