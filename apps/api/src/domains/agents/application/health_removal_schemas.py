"""Explicit all-kind deletion requires null; private server scope is never model-supplied."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from src.domains.agents.application.health_read_schemas import HealthSampleKind
from src.domains.health_metrics.removal_snapshot import HealthRemovalSnapshot


class HealthRemovalRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: HealthSampleKind | None


class HealthRemovalPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    health_samples_to_delete: HealthRemovalSnapshot


class HealthRemovalField(StrEnum):
    SAMPLES = "health_samples_to_delete"
