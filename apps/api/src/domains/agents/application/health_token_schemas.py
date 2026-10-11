"""The model can select an owned display UUID, never a raw token or another owner."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.domains.health_metrics.token_commands import HealthTokenSelection


class HealthTokenRevokeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    token_id: UUID


class HealthTokenRevokePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    health_token_to_revoke: HealthTokenSelection


class HealthTokenField(StrEnum):
    REVOKE = "health_token_to_revoke"
    CREATE = "health_token_to_create"
