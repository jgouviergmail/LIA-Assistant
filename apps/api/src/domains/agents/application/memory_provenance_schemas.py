"""A provenance read selects one identity, without scope or source injection."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MemoryProvenanceRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    memory_id: UUID
