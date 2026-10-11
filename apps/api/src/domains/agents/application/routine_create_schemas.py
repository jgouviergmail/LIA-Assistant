"""Strict Studio creation; target identity and timezone are resolved by preparation."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr

from src.domains.scheduled_actions.schemas import ConditionConfig, ScheduledActionCreate


class RoutineCondition(ConditionConfig):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RoutineCreateRequest(ScheduledActionCreate):
    model_config = ConfigDict(extra="forbid", frozen=True)
    condition_config: RoutineCondition | None = None
    requires_approval: StrictBool = False


class RoutineCreationValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    user_timezone: StrictStr
    configuration: RoutineCreateRequest


class RoutineCreatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    routine_to_create: RoutineCreationValues
