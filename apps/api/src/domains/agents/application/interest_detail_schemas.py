"""A single owned identity exposes source explanations and bounded provenance only."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.domains.interests.schemas import InterestExplanation
from src.domains.shared.schemas import ProvenanceResponse


class InterestDetailRead(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    interest_id: UUID


class InterestDetailProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    interest_id: UUID
    observed_at: datetime
    explanation: InterestExplanation
    provenance: ProvenanceResponse
