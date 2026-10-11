"""Only the source can construct a pin comparison snapshot."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr


class MemoryField(StrEnum):
    PIN = "memory_pin"
    CREATE = "memory_to_create"
    UPDATE = "memory_configuration"
    DELETE = "memory_to_delete"
    DELETE_ALL = "memories_to_delete"


class MemoryPinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    memory_id: UUID
    pinned: StrictBool


class MemoryPinSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    content: StrictStr
    category: StrictStr
    pinned: StrictBool
    created_at: datetime
    updated_at: datetime
    configuration_digest: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class MemoryPinValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    expected: MemoryPinSnapshot
    pinned: StrictBool


class MemoryPinPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    memory_pin: MemoryPinValues
