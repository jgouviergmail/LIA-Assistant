"""Source creation input and exact account quota context for one human approval."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.rag_spaces.schemas import RAGSpaceCreate


class SpaceCreateInput(RAGSpaceCreate):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SpaceCreateSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: SpaceCreateInput
    owned_count: StrictInt = Field(ge=0)
    max_spaces: StrictInt = Field(ge=1)

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            "configuration": self.request.model_dump(mode="json"),
            "owned_count": self.owned_count + (1 if after else 0),
            "max_spaces": self.max_spaces,
            "creation_requested": after,
            "active_on_creation": True,
            "document_count": 0,
        }


class SpaceCreatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    space_create: SpaceCreateSelection


class SpaceCreateField(StrEnum):
    CREATE = "space_create"


def canonical_space_creation(draft: ApplicationActionDraftContent) -> bool:
    selection = SpaceCreatePatch.model_validate(draft.intent).space_create
    return draft.before == {"space_create": selection.public_scope()} and draft.after == {
        "space_create": selection.public_scope(after=True)
    }
