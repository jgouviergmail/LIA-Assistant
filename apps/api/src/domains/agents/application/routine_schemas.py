"""Routine commands name a target and an explicit desired state."""

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr


class RoutineField(str, Enum):
    STATE = "routine_state"
    CREATE = "routine_to_create"
    DELETE = "routine_to_delete"
    UPDATE = "routine_configuration"
    RUN = "routine_to_run"


class RoutineStateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    routine_id: UUID
    enabled: StrictBool


class RoutineSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    title: StrictStr = Field(min_length=1, max_length=200)
    enabled: StrictBool
    configuration_digest: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class RoutineStateValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    expected: RoutineSnapshot
    enabled: StrictBool


class RoutineStatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    routine_state: RoutineStateValues
