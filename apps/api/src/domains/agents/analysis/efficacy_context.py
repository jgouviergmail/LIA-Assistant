"""Minimal turn-local attribution; contains no private scores or raw evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator

from src.domains.psyche.constants import EfficacyDomain
from src.domains.psyche.efficacy_contracts import EfficacyEpoch


class EfficacyAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    domains: tuple[EfficacyDomain, ...] = Field(default=(), max_length=2)
    ambiguous: bool = False
    verification_needed: bool = False

    @model_validator(mode="after")
    def unique_domains(self) -> EfficacyAnalysis:
        if len(set(self.domains)) != len(self.domains):
            raise ValueError("Duplicate cognitive domains")
        return self


class EfficacyTurnContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    owner_id: UUID
    run_id: str = Field(min_length=1, max_length=200)
    epoch: EfficacyEpoch
    analysis: EfficacyAnalysis
    collection_enabled: bool = True
    issued_at: AwareDatetime

    def valid_at(self, now: datetime) -> bool:
        return self.issued_at <= now.astimezone(UTC) < self.issued_at + timedelta(hours=24)


def read_analysis(raw: object) -> EfficacyAnalysis:
    try:
        return EfficacyAnalysis.model_validate(raw)
    except ValidationError:
        return EfficacyAnalysis()


def read_turn_context(raw: object) -> EfficacyTurnContext | None:
    try:
        return EfficacyTurnContext.model_validate(raw)
    except ValidationError:
        return None
