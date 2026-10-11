"""Strict sparse management edits, with comparison data constructed only by the source."""

from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.domains.agents.application.memory_create_schemas import MemoryCreateConfiguration
from src.domains.agents.application.memory_pin_schemas import MemoryPinSnapshot
from src.domains.memories.schemas import MemoryUpdate


class MemoryUpdateChanges(MemoryUpdate):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def refuse_explicit_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Omit an unchanged memory setting instead of null")
        return value

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Choose at least one memory setting")
        return self


class MemoryUpdateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    memory_id: UUID
    changes: MemoryUpdateChanges


class MemoryUpdateValues(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected: MemoryPinSnapshot
    configuration: MemoryCreateConfiguration
    changes: MemoryUpdateChanges


class MemoryUpdatePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    memory_configuration: MemoryUpdateValues
