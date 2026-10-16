"""Closed, immutable evidence contracts for the owner-private efficacy pilot.

Indices describe observed result and usefulness axes separately. They never
represent a probability that a future answer is factually correct.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from src.domains.psyche.constants import (
    EFFICACY_MAX_EPISODES,
    EFFICACY_MIN_SAMPLES,
    EFFICACY_WINDOW_DAYS,
    EfficacyDomain,
)

Count = Annotated[int, Field(strict=True, ge=0, le=EFFICACY_MAX_EPISODES)]
NullableScore = Annotated[float | None, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
RunId = Annotated[str, Field(strict=True, min_length=1, max_length=128, pattern=r"^\S+$")]
Fingerprint = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]


class EfficacyVerdict(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    EXCLUDED = "excluded"


class EfficacyReason(StrEnum):
    GOAL_SATISFIED = "goal_satisfied"
    ATTRIBUTABLE_FAILURE = "attributable_failure"
    INCOMPLETE_COVERAGE = "incomplete_coverage"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    EXTERNAL_FAILURE = "external_failure"
    HUMAN_DECISION = "human_decision"
    UNSUPPORTED_DOMAIN = "unsupported_domain"


class EfficacyFeedback(StrEnum):
    HELPFUL = "helpful"
    UNHELPFUL = "unhelpful"


class EfficacyPolicyReason(StrEnum):
    INFLUENCE_DISABLED = "influence_disabled"
    NO_ADJUSTMENT = "no_adjustment"
    VERIFICATION_NEEDED = "verification_needed"
    VERIFICATION_UNAVAILABLE = "verification_unavailable"
    CLARIFICATION_NEEDED = "clarification_needed"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EfficacyEpoch(_FrozenModel):
    state_id: UUID
    generation: UUID


class EfficacyObservation(_FrozenModel):
    domain: EfficacyDomain
    verdict: EfficacyVerdict
    reason: EfficacyReason


class _EpisodeFields(_FrozenModel):
    run_id: RunId
    message_id: UUID
    terminal_at: AwareDatetime
    observations: tuple[EfficacyObservation, ...] = Field(max_length=2)

    @field_validator("terminal_at")
    @classmethod
    def normalize_terminal_time(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @field_validator("observations")
    @classmethod
    def unique_domains(
        cls, value: tuple[EfficacyObservation, ...]
    ) -> tuple[EfficacyObservation, ...]:
        if len({item.domain for item in value}) != len(value):
            raise ValueError("An episode can observe each domain only once")
        return value


class EfficacyEpisodeInput(_EpisodeFields):
    epoch: EfficacyEpoch
    config_fingerprint: Fingerprint


class EfficacyEpisodeView(_EpisodeFields):
    """One canonical episode already scoped to an owner and generation by storage."""

    feedback: EfficacyFeedback | None = None


class EfficacyResultCounts(_FrozenModel):
    success: Count = 0
    failure: Count = 0
    partial: Count = 0
    unknown: Count = 0


class EfficacyFeedbackCounts(_FrozenModel):
    helpful: Count = 0
    unhelpful: Count = 0


class EfficacyDomainProfile(_FrozenModel):
    domain: EfficacyDomain
    status: Literal["unobserved", "learning", "observed"]
    results: EfficacyResultCounts
    feedback: EfficacyFeedbackCounts
    result_count: Count
    feedback_count: Count
    result_score: NullableScore
    feedback_score: NullableScore
    last_observed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def coherent_axes(self) -> Self:
        if self.result_count != self.results.success + self.results.failure:
            raise ValueError("Result count must contain scorable outcomes only")
        if self.feedback_count != self.feedback.helpful + self.feedback.unhelpful:
            raise ValueError("Feedback count must match the active explicit feedback")
        for count, score in (
            (self.result_count, self.result_score),
            (self.feedback_count, self.feedback_score),
        ):
            if (count == 0) != (score is None):
                raise ValueError("An index requires observations on its own axis")
        count = max(self.result_count, self.feedback_count)
        expected = (
            "observed" if count >= EFFICACY_MIN_SAMPLES else "learning" if count else "unobserved"
        )
        if self.status != expected:
            raise ValueError("Status must reflect the independently qualified sample size")
        return self


class EfficacyProfile(_FrozenModel):
    version: Literal[1] = 1
    window_days: Annotated[int, Field(strict=True, ge=1, le=EFFICACY_WINDOW_DAYS)] = (
        EFFICACY_WINDOW_DAYS
    )
    collection_enabled: Annotated[bool, Field(strict=True)] = True
    influence_enabled: Annotated[bool, Field(strict=True)] = True
    unassigned_feedback_count: Count = 0
    domains: tuple[EfficacyDomainProfile, ...] = Field(
        min_length=len(EfficacyDomain), max_length=len(EfficacyDomain)
    )

    @field_validator("domains")
    @classmethod
    def complete_canonical_domains(
        cls, value: tuple[EfficacyDomainProfile, ...]
    ) -> tuple[EfficacyDomainProfile, ...]:
        if tuple(item.domain for item in value) != tuple(EfficacyDomain):
            raise ValueError("Profile must contain each canonical domain in canonical order")
        return value


class EfficacyPolicy(_FrozenModel):
    action: Literal["none", "verify", "clarify", "state_limit"] = "none"
    domains: tuple[EfficacyDomain, ...] = Field(default=(), max_length=2)
    reason: EfficacyPolicyReason = EfficacyPolicyReason.NO_ADJUSTMENT

    @field_validator("domains")
    @classmethod
    def unique_domains(cls, value: tuple[EfficacyDomain, ...]) -> tuple[EfficacyDomain, ...]:
        if len(set(value)) != len(value):
            raise ValueError("Policy domains must be unique")
        return value

    @model_validator(mode="after")
    def coherent_decision(self) -> Self:
        expected = {
            "verify": EfficacyPolicyReason.VERIFICATION_NEEDED,
            "clarify": EfficacyPolicyReason.CLARIFICATION_NEEDED,
            "state_limit": EfficacyPolicyReason.VERIFICATION_UNAVAILABLE,
        }
        if self.action == "none":
            if self.domains or self.reason not in (
                EfficacyPolicyReason.NO_ADJUSTMENT,
                EfficacyPolicyReason.INFLUENCE_DISABLED,
            ):
                raise ValueError("A neutral policy must not carry an active adjustment")
            return self
        if not self.domains or self.reason != expected[self.action]:
            raise ValueError("A policy action requires relevant domains and its exact reason")
        return self
