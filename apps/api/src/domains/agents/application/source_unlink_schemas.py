"""Exact source removal retains documents and never accepts storage or deletion parameters."""

from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, model_validator

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.space_update_schemas import SpaceUpdateTarget


class SourceUnlinkInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    space_id: UUID = Field(description="Real owned personal destination space")
    source_id: UUID = Field(description="Exact linked source id from the current space reader")
    kind: Literal["drive", "mail"] = Field(description="Drive folder or Gmail label source")


class SourceUnlinkSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request: SourceUnlinkInput = Field(description="Exact retained-document removal request")
    space: SpaceUpdateTarget = Field(description="Public owned destination metadata")
    source_name: str = Field(description="Literal Source display name")
    sync_status: str = Field(description="Observed nonrunning source lifecycle")
    documents: StrictInt = Field(ge=0, description="Exact observed linked document count")
    documents_digest: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        repr=False,
        description="Private whole-space document identity witness",
    )
    state_digest: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        repr=False,
        description="Private whole-row source and parent witness",
    )

    @model_validator(mode="after")
    def exact_destination(self) -> Self:
        if self.space.id != self.request.space_id:
            raise ValueError("The public destination must be the exact requested space")
        return self

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            "space": self.space.model_dump(mode="json"),
            "source_id": str(self.request.source_id),
            "kind": self.request.kind,
            "source_name": self.source_name,
            "sync_status": self.sync_status,
            "documents": self.documents,
            "documents_retained": True,
            "source_removed": after,
        }


class SourceUnlinkPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_to_unlink: SourceUnlinkSelection = Field(
        description="Exact Source scope; no file deletion"
    )


class SourceUnlinkField(StrEnum):
    SOURCE_TO_UNLINK = "source_to_unlink"


def canonical_source_unlink(draft: ApplicationActionDraftContent) -> bool:
    selected = SourceUnlinkPatch.model_validate(draft.intent).source_to_unlink
    return draft.before == {"source_to_unlink": selected.public_scope()} and draft.after == {
        "source_to_unlink": selected.public_scope(after=True)
    }
