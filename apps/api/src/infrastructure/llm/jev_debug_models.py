"""Bounded, typed native diagnostics; no credential or raw provider-error body."""

import json
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from src.infrastructure.llm.typesafe_client import (
    ChoiceAnswer,
    ChoiceQuestion,
    InvalidResponseReason,
)

CONTEXT_CHARACTERS = 6000
RESPONSE_CANDIDATES = 10
TRACE_LIMIT = 30
TRACE_TTL_SECONDS = 3600


class ContextPreview(BaseModel):
    text: str = Field(max_length=CONTEXT_CHARACTERS, description="Formatted request preview.")
    original_characters: int = Field(ge=0, description="Length before the display limit.")
    omitted_characters: int = Field(ge=0, description="Characters not retained.")


class CandidateProbability(BaseModel):
    key: str = Field(max_length=100, description="Opaque candidate key.")
    label: str = Field(max_length=240, description="Bounded candidate description.")
    probability: float = Field(ge=0, le=1, allow_inf_nan=False, description="Provider probability.")


class ChoicePreview(BaseModel):
    choice: str = Field(max_length=100, description="Provider's chosen key.")
    choice_label: str = Field(max_length=240, description="Meaning of the chosen key.")
    confidence: float = Field(
        ge=0, le=1, allow_inf_nan=False, description="Concentration, not accuracy."
    )
    probabilities: list[CandidateProbability] = Field(
        max_length=RESPONSE_CANDIDATES, description="Highest probabilities first."
    )
    omitted_candidates: int = Field(ge=0, description="Candidates outside this preview.")


JevAction = Literal[
    "pending", "selected", "preview", "observed", "fallback", "aborted", "cancelled"
]
AppliedVerdict = Literal["match", "non_match", "unknown"]


class JevCollectionCoverage(BaseModel):
    """Global collection counts shared by its native batches, never summed across traces."""

    model_config = ConfigDict(extra="forbid")
    candidate_count: int = Field(ge=0, description="All canonical collection candidates.")
    evaluated_count: int = Field(ge=0, description="Candidates submitted across all batches.")
    unevaluated_count: int = Field(ge=0, description="Candidates not submitted to JEV.")
    omitted_count: int = Field(ge=0, description="Unevaluated candidates outside the preview.")
    unknown_count: int = Field(ge=0, description="Evaluated candidates unknown after gates.")
    batch_index: int | None = Field(default=None, ge=1, description="This batch, one-based.")
    batch_count: int | None = Field(default=None, ge=1, description="Collection native batches.")

    @model_validator(mode="after")
    def consistent_counts(self) -> JevCollectionCoverage:
        if self.candidate_count != self.evaluated_count + self.unevaluated_count:
            raise ValueError("Collection coverage must partition candidates.")
        if self.unknown_count > self.evaluated_count or self.omitted_count > self.unevaluated_count:
            raise ValueError("Collection subsets exceed their population.")
        if (self.batch_index is None) != (self.batch_count is None):
            raise ValueError("Batch index and count must be supplied together.")
        if self.batch_index is not None and self.batch_count is not None:
            if self.batch_index > self.batch_count:
                raise ValueError("Batch index exceeds count.")
        return self


class JevCallTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID = Field(description="One native attempt; decision updates keep this identity.")
    run_id: str = Field(
        max_length=255, description="Actual accounting run, including background runs."
    )
    caller: str = Field(max_length=100, description="Registered calling configuration slot.")
    usage: str = Field(max_length=100, description="Registered JEV usage.")
    started_at: datetime = Field(description="UTC call start.")
    requested_model: str = Field(max_length=100, description="Model sent to TypeSafe.")
    reported_model: str | None = Field(default=None, max_length=100, description="Model returned.")
    duration_ms: float = Field(
        default=0, ge=0, allow_inf_nan=False, description="Native path duration."
    )
    context: ContextPreview = Field(description="Bounded state and question actually submitted.")
    observed_result: ContextPreview | None = Field(
        default=None, description="Existing extractor model's proposal before write validation."
    )
    collection_coverage: JevCollectionCoverage | None = Field(
        default=None, description="Global coverage after batch join; absent on historical traces."
    )
    response: ChoicePreview | None = Field(default=None, description="Validated provider response.")
    responses: dict[str, ChoicePreview] = Field(
        default_factory=dict, max_length=24, description="Batch answers by their request key."
    )
    outcome: str = Field(
        default="pending", max_length=100, description="Safe result or failure code."
    )
    invalid_response_reason: InvalidResponseReason | None = Field(
        default=None, description="Closed validation code, never raw response or error text."
    )
    status_code: int | None = Field(default=None, description="HTTP error status when available.")
    action: JevAction = Field(
        default="pending", description="Actual consumer branch, separate from the answer."
    )
    action_target: str | None = Field(
        default=None, max_length=240, description="Selected template or fallback slot."
    )
    applied_decisions: dict[str, AppliedVerdict] = Field(
        default_factory=dict, max_length=100, description="Consumer verdict after confidence gates."
    )
    decision_labels: dict[
        Annotated[str, Field(max_length=100)], Annotated[str, Field(max_length=180)]
    ] = Field(
        default_factory=dict, max_length=24, description="Bounded source titles by question key."
    )
    input_tokens: int | None = Field(default=None, ge=0, description="Reported usage if available.")
    output_tokens: int | None = Field(
        default=None, ge=0, description="Reported usage if available."
    )
    cost_eur: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="Cost at configured tariff if usage is known.",
    )


class JevTracePage(BaseModel):
    calls: list[JevCallTrace] = Field(description="This account's retained attempts, newest first.")
    limit: int = Field(default=TRACE_LIMIT, description="Maximum retained calls.")
    retention_seconds: int = Field(default=TRACE_TTL_SECONDS, description="Temporary retention.")


def context_preview(value: JsonValue) -> ContextPreview:
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    return ContextPreview(
        text=text[:CONTEXT_CHARACTERS],
        original_characters=len(text),
        omitted_characters=max(0, len(text) - CONTEXT_CHARACTERS),
    )


def choice_preview(
    answer: ChoiceAnswer, question: ChoiceQuestion, *, limit: int = RESPONSE_CANDIDATES
) -> ChoicePreview:
    ordered = sorted(answer.probabilities.items(), key=lambda item: item[1], reverse=True)
    return ChoicePreview(
        choice=answer.choice,
        choice_label=question.criteria.get(answer.choice, answer.choice)[:240],
        confidence=answer.confidence,
        probabilities=[
            CandidateProbability(
                key=key, label=question.criteria.get(key, key)[:240], probability=probability
            )
            for key, probability in ordered[:limit]
        ],
        omitted_candidates=max(0, len(ordered) - limit),
    )
