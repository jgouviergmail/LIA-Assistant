"""Typed complete interest counts and source UI settings accompany bounded pages."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domains.interests.models import InterestCategory, InterestStatus
from src.domains.interests.schemas import InterestListResponse, InterestSettingsResponse


class InterestRead(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    interest_id: UUID | None = None
    category: InterestCategory | None = None
    status: InterestStatus | None = None
    after_id: UUID | None = None
    limit: int = Field(default=5, ge=1, le=50, strict=True)

    @model_validator(mode="after")
    def refuse_mixed_selection(self) -> InterestRead:
        if self.interest_id is not None and any(
            value is not None for value in (self.category, self.status, self.after_id)
        ):
            raise ValueError("Select one interest or a filtered page")
        return self


class InterestProjection(InterestListResponse):
    model_config = ConfigDict(extra="forbid")
    settings: InterestSettingsResponse
    timezone: str
    observed_at: datetime
    returned_count: int = Field(ge=0)
    total_available: int = Field(ge=0)
    by_category: dict[InterestCategory, int]
    truncated: bool
    next_cursor: UUID | None = None
