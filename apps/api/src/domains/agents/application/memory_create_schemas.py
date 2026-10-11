"""Source creation vocabulary and constraints, with strict native values."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool

from src.domains.memories.schemas import MemoryCreate


class MemoryCreateConfiguration(MemoryCreate):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class MemoryCreationValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    configuration: MemoryCreateConfiguration
    pinned: StrictBool


class MemoryCreatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    memory_to_create: MemoryCreationValues
