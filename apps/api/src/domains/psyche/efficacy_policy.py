"""History can add a bounded work adjustment, never dismiss present facts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from src.domains.psyche.constants import EFFICACY_MIN_SAMPLES, EfficacyDomain
from src.domains.psyche.efficacy_contracts import (
    EfficacyDomainProfile,
    EfficacyPolicy,
    EfficacyPolicyReason,
    EfficacyProfile,
)


def _needs_adjustment(entry: EfficacyDomainProfile, axis: Literal["result", "feedback"]) -> bool:
    # Repeated partial coverage supports a targeted check, without turning
    # partial into a failure or assigning an invented numeric score.
    if axis == "result" and entry.results.partial >= EFFICACY_MIN_SAMPLES:
        if entry.results.partial > entry.results.success:
            return True
    count, score = (
        (entry.result_count, entry.result_score)
        if axis == "result"
        else (entry.feedback_count, entry.feedback_score)
    )
    return count >= EFFICACY_MIN_SAMPLES and score is not None and score < 0.5


def _adjustment_domains(
    profile: EfficacyProfile,
    selected: tuple[EfficacyDomain, ...],
    axis: Literal["result", "feedback"],
) -> tuple[EfficacyDomain, ...]:
    return tuple(
        entry.domain
        for entry in profile.domains
        if entry.domain in selected and _needs_adjustment(entry, axis)
    )


def choose_policy(
    profile: EfficacyProfile,
    domains: Sequence[EfficacyDomain | str],
    *,
    current_gap: bool,
    ambiguous: bool,
    can_verify: bool,
    budget_available: bool,
) -> EfficacyPolicy:
    """Choose one adjustment; mandatory verification remains the existing system's job."""
    selected = tuple(dict.fromkeys(EfficacyDomain(domain) for domain in domains))
    if len(selected) > 2:
        raise ValueError("Policy accepts at most two relevant cognitive domains")
    if not profile.influence_enabled:
        return EfficacyPolicy(reason=EfficacyPolicyReason.INFLUENCE_DISABLED)
    verification_domains = _adjustment_domains(profile, selected, "result")
    if current_gap and verification_domains:
        if can_verify and budget_available:
            return EfficacyPolicy(
                action="verify",
                domains=verification_domains,
                reason=EfficacyPolicyReason.VERIFICATION_NEEDED,
            )
        return EfficacyPolicy(
            action="state_limit",
            domains=verification_domains,
            reason=EfficacyPolicyReason.VERIFICATION_UNAVAILABLE,
        )
    weak_feedback = _adjustment_domains(profile, selected, "feedback")
    if ambiguous and weak_feedback:
        return EfficacyPolicy(
            action="clarify",
            domains=weak_feedback,
            reason=EfficacyPolicyReason.CLARIFICATION_NEEDED,
        )
    return EfficacyPolicy()


def render_policy(policy: EfficacyPolicy) -> str:
    """Serialize closed decision data; versioned prompts own all instructions."""
    return policy.model_dump_json()
