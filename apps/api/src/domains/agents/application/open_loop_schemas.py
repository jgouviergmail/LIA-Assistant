"""Source commitment fields and bounded complete-count paging, without origin references."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domains.open_loops.models import OpenLoopStatus
from src.domains.open_loops.schemas import OpenLoopListResponse


class OpenLoopRead(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: OpenLoopStatus | None = OpenLoopStatus.OPEN
    after_id: UUID | None = None
    limit: int = Field(default=5, ge=1, le=50, strict=True)


class OpenLoopProjection(OpenLoopListResponse):
    model_config = ConfigDict(frozen=True, extra="forbid")
    timezone: str
    observed_at: datetime
    returned_count: int = Field(ge=0)
    truncated: bool
    next_cursor: UUID | None = None
