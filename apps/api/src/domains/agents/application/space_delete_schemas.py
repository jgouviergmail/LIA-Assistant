"""Exact personal space deletion names every document and linked synchronization source."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.space_update_schemas import SpaceUpdateTarget


class SpaceDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    space_id: UUID


class SpaceDeleteDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)
    id: UUID
    original_filename: str
    status: str
    source_type: str
    file_size: StrictInt


class SpaceDeleteSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    name: str


class SpaceDeleteSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: SpaceDeleteInput
    space: SpaceUpdateTarget
    items: list[SpaceDeleteDocument]
    drive_sources: list[SpaceDeleteSource]
    mail_sources: list[SpaceDeleteSource]
    chunks: StrictInt = Field(ge=0)
    owned_spaces: StrictInt = Field(ge=1)
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            "space": self.space.model_dump(mode="json"),
            "items": [item.model_dump(mode="json") for item in self.items],
            "documents": len(self.items),
            "chunks": self.chunks,
            "drive_sources": [source.model_dump(mode="json") for source in self.drive_sources],
            "mail_sources": [source.model_dump(mode="json") for source in self.mail_sources],
            "deletion_requested": after,
        }


class SpaceDeletePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    space_delete: SpaceDeleteSelection


class SpaceDeleteField(StrEnum):
    DELETE = "space_delete"


def canonical_space_deletion(draft: ApplicationActionDraftContent) -> bool:
    selected = SpaceDeletePatch.model_validate(draft.intent).space_delete
    return draft.before == {"space_delete": selected.public_scope()} and draft.after == {
        "space_delete": selected.public_scope(after=True)
    }
