"""Source explanation data remains typed JSON and never accepts another account."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from src.domains.habits.schemas import HabitExplanationResponse


class HabitDetailRead(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    habit_id: UUID


class HabitDetailProjection(HabitExplanationResponse):
    model_config = ConfigDict(frozen=True, extra="forbid")
    payload: dict[str, JsonValue]
    habit_id: UUID
    observed_at: datetime
