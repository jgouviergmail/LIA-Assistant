"""The public personality contracts exclude administrative prompts and traits."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domains.personalities.schemas import PersonalityListResponse, UserPersonalityResponse


class PersonalityRead(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    limit: int = Field(default=5, ge=1, le=50, strict=True)
    after_id: UUID | None = None


class PersonalityProjection(PersonalityListResponse, UserPersonalityResponse):
    model_config = ConfigDict(frozen=True, extra="forbid")
    returned_count: int = Field(ge=0)
    truncated: bool
    next_cursor: UUID | None = None
    language: str
    observed_at: datetime
