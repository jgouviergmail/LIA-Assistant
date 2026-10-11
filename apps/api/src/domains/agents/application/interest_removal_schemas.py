"""A source-built deletion fact has no model-supplied owner or configurable scope."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.domains.agents.application.interest_update_schemas import (
    InterestEditSnapshot,
)
from src.domains.interests.management_schemas import InterestConfiguration


class InterestDeleteRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    interest_id: UUID


class InterestDeleteValues(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected: InterestEditSnapshot
    configuration: InterestConfiguration


class InterestDeletePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    interest_to_delete: InterestDeleteValues
