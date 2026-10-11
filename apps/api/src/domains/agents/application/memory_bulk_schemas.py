"""Bounded confirmations contain counts and a private digest, never a list of saved facts."""

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt


class MemoryBulkDeleteRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    preserve_pinned: StrictBool = False


class MemoryBulkSnapshot(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    preserve_pinned: StrictBool
    selected_count: StrictInt = Field(ge=0)
    preserved_count: StrictInt = Field(ge=0)
    pinned_count: StrictInt = Field(ge=0)
    procedural_count: StrictInt = Field(ge=0)
    invalidated_count: StrictInt = Field(ge=0)
    by_category: dict[str, int]
    selection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class MemoryBulkDeletePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    memories_to_delete: MemoryBulkSnapshot
