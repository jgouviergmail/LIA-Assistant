"""Strict Studio deltas distinguish omission from clearing a required value."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr, field_validator, model_validator

from src.domains.agents.application.routine_create_schemas import (
    RoutineCondition,
    RoutineCreateRequest,
)
from src.domains.agents.application.routine_schemas import RoutineSnapshot
from src.domains.scheduled_actions.schemas import ScheduledActionUpdate


class RoutineUpdateChanges(ScheduledActionUpdate):
    model_config = ConfigDict(extra="forbid", frozen=True)
    condition_config: RoutineCondition | None = None
    requires_approval: StrictBool | None = None

    @field_validator(
        "title",
        "action_prompt",
        "trigger_kind",
        "requires_approval",
        "execution_mode",
        mode="before",
    )
    @classmethod
    def refuse_required_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Omit a required routine setting rather than clearing it")
        return value

    @model_validator(mode="after")
    def require_delta(self) -> RoutineUpdateChanges:
        if not self.model_fields_set:
            raise ValueError("Choose at least one routine setting")
        return self


class RoutineUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    routine_id: UUID
    changes: RoutineUpdateChanges


class RoutineUpdateValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    expected: RoutineSnapshot
    user_timezone: StrictStr
    enabled: StrictBool
    configuration: RoutineCreateRequest
    changes: RoutineUpdateChanges


class RoutineUpdatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    routine_configuration: RoutineUpdateValues
