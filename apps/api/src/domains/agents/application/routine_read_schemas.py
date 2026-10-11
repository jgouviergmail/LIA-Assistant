"""Finite read views reuse the Studio's typed public data and clock metadata."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domains.scheduled_actions.schemas import (
    ScheduledActionListResponse,
    ScheduledActionWeekResponse,
)


class RoutineRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    view: Literal["settings", "week"] = "settings"
    routine_id: UUID | None = None
    after_id: UUID | None = None
    limit: int = Field(default=5, ge=1, le=50, strict=True)

    @model_validator(mode="after")
    def refuse_mixed_selection(self) -> RoutineRead:
        if self.routine_id is not None and self.after_id is not None:
            raise ValueError("Choose one routine or a page continuation")
        return self


class RoutineProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    view: Literal["settings", "week"]
    settings: ScheduledActionListResponse | None = None
    week: ScheduledActionWeekResponse | None = None
    returned_count: int = Field(ge=0)
    total_available: int = Field(ge=0)
    truncated: bool = False
    next_cursor: UUID | None = None
