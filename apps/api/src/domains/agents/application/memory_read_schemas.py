"""Explicit memory management is bounded and separate from automatic semantic recall."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domains.memories.schemas import MemoryCategoryType, MemoryResponse


class MemoryRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    memory_id: UUID | None = None
    category: MemoryCategoryType | None = None
    after_id: UUID | None = None
    limit: int = Field(default=5, ge=1, le=50, strict=True)

    @model_validator(mode="after")
    def refuse_mixed_selection(self) -> MemoryRead:
        if self.memory_id is not None and (self.category is not None or self.after_id is not None):
            raise ValueError("Select one memory or a filtered page")
        return self


class MemoryProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memories: list[MemoryResponse]
    automatic_use_enabled: bool
    returned_count: int = Field(ge=0)
    total_available: int = Field(ge=0)
    by_category: dict[str, int]
    truncated: bool
    next_cursor: UUID | None = None
