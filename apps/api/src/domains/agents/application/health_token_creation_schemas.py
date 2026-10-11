"""Creation accepts only the existing source label; no client secret or authority."""

from pydantic import BaseModel, ConfigDict

from src.domains.health_metrics.schemas import HealthMetricTokenCreateRequest


class HealthTokenCreateRequest(HealthMetricTokenCreateRequest):
    model_config = ConfigDict(frozen=True, extra="forbid")


class HealthTokenCreatePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    health_token_to_create: HealthTokenCreateRequest
