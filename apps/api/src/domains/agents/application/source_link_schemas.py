"""Only a real owned destination and provider identity enter the model's link request."""

from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, model_validator

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.space_update_schemas import SpaceUpdateTarget


class SourceLinkInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    space_id: UUID = Field(description="Real current-account personal destination space")
    kind: Literal["drive", "mail"] = Field(description="Drive folder or Gmail user label")
    provider_id: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Real Drive folder id or Gmail Label_ id from the live source picker; no URL or query",
    )

    @model_validator(mode="after")
    def user_label(self) -> Self:
        if self.kind == "mail" and not self.provider_id.startswith("Label_"):
            raise ValueError("Only Gmail user-label identities are offered by this source picker")
        return self


class SourceLinkSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request: SourceLinkInput
    space: SpaceUpdateTarget
    source_name: str = Field(
        min_length=1, max_length=500, description="Literal current provider name"
    )
    owned_count: StrictInt = Field(ge=0, description="Exact current same-kind source count")
    max_sources: StrictInt = Field(ge=1, description="Current Source same-kind source limit")
    state_digest: str = Field(
        pattern=r"^[0-9a-f]{64}$", repr=False, description="Private whole-parent authority witness"
    )

    @model_validator(mode="after")
    def exact_destination(self) -> Self:
        if self.space.id != self.request.space_id or self.owned_count >= self.max_sources:
            raise ValueError("Source destination or available capacity differs")
        return self

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            "space": self.space.model_dump(mode="json"),
            "kind": self.request.kind,
            "provider_id": self.request.provider_id,
            "source_name": self.source_name,
            "owned_count": self.owned_count + int(after),
            "max_sources": self.max_sources,
            "source_linked": after,
            "automatic_sync": after,
            "indexed_now": False,
        }


class SourceLinkPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_to_link: SourceLinkSelection


class SourceLinkField(StrEnum):
    SOURCE_TO_LINK = "source_to_link"


def canonical_source_link(draft: ApplicationActionDraftContent) -> bool:
    selected = SourceLinkPatch.model_validate(draft.intent).source_to_link
    return draft.before == {"source_to_link": selected.public_scope()} and draft.after == {
        "source_to_link": selected.public_scope(after=True)
    }
