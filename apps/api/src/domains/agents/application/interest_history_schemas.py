"""Source notification fields, bounded stable paging and complete owned totals."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domains.interests.schemas import InterestNotificationHistoryResponse


class InterestHistoryRead(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    after_id: UUID | None = None
    limit: int = Field(default=5, ge=1, le=50, strict=True)


class InterestHistoryProjection(InterestNotificationHistoryResponse):
    model_config = ConfigDict(extra="forbid")
    timezone: str
    observed_at: datetime
    returned_count: int = Field(ge=0)
    truncated: bool
    next_cursor: UUID | None = None
