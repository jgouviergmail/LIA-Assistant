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
    # Spec 2026-10-29 D9: the names of the MCP servers the routine confirms for
    # itself — display only, for the card; the keys are in the snapshot's digest.
    mcp_preapproval: tuple[StrictStr, ...]


class RoutineRunPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    routine_to_run: RoutineRunValues
