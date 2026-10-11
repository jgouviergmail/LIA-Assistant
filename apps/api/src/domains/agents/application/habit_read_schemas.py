"""The source overview is preserved; habit payloads are typed JSON and pages are explicit."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.domains.habits.schemas import HabitResponse, HabitsOverviewResponse


class HabitRead(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    limit: int = Field(default=5, ge=1, le=50, strict=True)
    after_id: UUID | None = None


class HabitProjection(HabitResponse):
    model_config = ConfigDict(frozen=True, extra="forbid")
    payload: dict[str, JsonValue]


class HabitsProjection(HabitsOverviewResponse):
    model_config = ConfigDict(frozen=True, extra="forbid")
    habits: list[HabitProjection] = Field(default_factory=list)
    total: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    truncated: bool
    next_cursor: UUID | None = None
    timezone: str
    observed_at: datetime
