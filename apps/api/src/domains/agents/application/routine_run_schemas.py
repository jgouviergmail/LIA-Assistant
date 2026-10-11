"""Manual execution selects one exact owned routine, never a new instruction."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictStr

from src.domains.agents.application.routine_create_schemas import RoutineCreateRequest
from src.domains.agents.application.routine_schemas import RoutineSnapshot


class RoutineRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    routine_id: UUID


class RoutineRunValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    expected: RoutineSnapshot
    configuration: RoutineCreateRequest
    user_timezone: StrictStr


class RoutineRunPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    routine_to_run: RoutineRunValues
