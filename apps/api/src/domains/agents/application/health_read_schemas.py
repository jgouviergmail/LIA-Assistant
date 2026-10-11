"""Source public DTOs enrich observational health tools without exposing ingestion secrets."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core.constants import HEALTH_METRICS_KINDS
from src.domains.health_metrics.schemas import HealthMetricTokenListResponse, HealthSampleRow

HealthSampleKind = Literal["heart_rate", "steps"]


class HealthSamplesRead(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: HealthSampleKind | None = None
    from_ts: datetime | None = None
    to_ts: datetime | None = None
    limit: int = Field(default=20, ge=1, le=100, strict=True)
    after_id: UUID | None = None
    as_of: datetime | None = None

    @field_validator("from_ts", "to_ts", "as_of")
    @classmethod
    def aware_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Use an ISO 8601 timestamp with timezone")
        return value

    @model_validator(mode="after")
    def valid_window(self) -> HealthSamplesRead:
        if self.from_ts is not None and self.to_ts is not None and self.from_ts >= self.to_ts:
            raise ValueError("Window start must precede its exclusive end")
        if self.after_id is not None and self.as_of is None:
            raise ValueError("Continue with the previous page's as_of")
        return self


class HealthSamplesProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    samples: list[HealthSampleRow]
    total: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    truncated: bool
    next_cursor: UUID | None = None
    as_of: datetime
    observed_at: datetime


class HealthTokensProjection(HealthMetricTokenListResponse):
    model_config = ConfigDict(frozen=True, extra="forbid")
    total: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    truncated: bool
    next_cursor: UUID | None = None
    as_of: datetime
    observed_at: datetime


class HealthTokensRead(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    limit: int = Field(default=20, ge=1, le=100, strict=True)
    after_id: UUID | None = None
    as_of: datetime | None = None

    @field_validator("as_of")
    @classmethod
    def aware_time(cls, value: datetime | None) -> datetime | None:
        return HealthSamplesRead.aware_time(value)

    @model_validator(mode="after")
    def valid_cursor(self) -> HealthTokensRead:
        if self.after_id is not None and self.as_of is None:
            raise ValueError("Continue with the previous page's as_of")
        return self


if set(HEALTH_METRICS_KINDS) != {"heart_rate", "steps"}:
    raise AssertionError(
        "Review public source DTOs and management consent when a health kind is added"
    )
