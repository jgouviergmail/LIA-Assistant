"""Routine deletion names one owned frozen configuration, never an arbitrary endpoint."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.domains.agents.application.routine_schemas import RoutineSnapshot


class RoutineDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    routine_id: UUID


class RoutineDeletePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    routine_to_delete: RoutineSnapshot
