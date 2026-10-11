"""Source psyche projections use typed JSON and explicit missing state, never a invented baseline."""

from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue

from src.domains.psyche.schemas import (
    ActiveEmotionResponse,
    PsycheExpressionResponse,
    PsycheHistoryEntry,
    PsycheSettingsResponse,
    PsycheStateResponse,
)


class PsycheRead(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    limit: int = Field(default=5, ge=1, le=50, strict=True)
    after_id: UUID | None = None
    hours: int | None = Field(default=None, ge=1, le=2160, strict=True)
    snapshot_type: str | None = Field(default=None, min_length=1, max_length=30, strict=True)
    as_of: AwareDatetime | None = None


class PsycheStateProjection(PsycheStateResponse):
    model_config = ConfigDict(frozen=True, extra="forbid")
    active_emotions: list[ActiveEmotionResponse] = Field(default_factory=list)
    self_efficacy: dict[str, JsonValue] = Field(default_factory=dict)


class PsycheExpressionProjection(PsycheExpressionResponse):
    model_config = ConfigDict(frozen=True, extra="forbid")
    active_emotions: list[dict[str, JsonValue]] = Field(default_factory=list)


class PsycheHistoryProjection(PsycheHistoryEntry):
    model_config = ConfigDict(frozen=True, extra="forbid")
    trait_snapshot: dict[str, JsonValue] | None


class PsycheProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    settings: PsycheSettingsResponse
    state: PsycheStateProjection | None
    expression: PsycheExpressionProjection | None
    history: list[PsycheHistoryProjection]
    total: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    truncated: bool
    next_cursor: UUID | None = None
    as_of: datetime
    observed_at: datetime
