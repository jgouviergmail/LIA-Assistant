"""Only the source supplies an exact deletion snapshot."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.domains.agents.application.memory_pin_schemas import MemoryPinSnapshot


class MemoryDeleteRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    memory_id: UUID


class MemoryDeletePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    memory_to_delete: MemoryPinSnapshot
