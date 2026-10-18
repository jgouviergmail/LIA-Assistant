"""Detached observations: identities never enter model instructions or answers."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.core.content_classification import EvidenceScope


class ClassificationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    identity: str = Field(min_length=1, max_length=1024)
    kind: Literal["email", "event"]
    container_id: str = Field(max_length=2048)
    item_id: str = Field(min_length=1, max_length=2048)
    occurrence: str = Field(max_length=1024)
    revision: str = Field(max_length=1024)
    evidence_scope: EvidenceScope
    evidence: dict[str, JsonValue]
