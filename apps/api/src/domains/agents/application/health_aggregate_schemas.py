"""The source chart periods and aware window are published with a bounded result size."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.domains.agents.application.health_read_schemas import HealthSamplesRead
from src.domains.health_metrics.aggregator import PeriodLiteral

HEALTH_CHART_MAX_BUCKETS = 200


class HealthAggregateRead(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    period: PeriodLiteral = "day"
    from_ts: datetime | None = None
    to_ts: datetime | None = None

    @field_validator("from_ts", "to_ts")
    @classmethod
    def aware_time(cls, value: datetime | None) -> datetime | None:
        return HealthSamplesRead.aware_time(value)

    @model_validator(mode="after")
    def valid_window(self) -> HealthAggregateRead:
        if self.from_ts is not None and self.to_ts is not None and self.from_ts >= self.to_ts:
            raise ValueError("Window start must precede its exclusive end")
        return self
