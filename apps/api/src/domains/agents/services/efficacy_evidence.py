"""Compact, conservative learning evidence from the current terminal graph output."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.domains.agents.analysis.efficacy_context import EfficacyTurnContext, read_turn_context
from src.domains.agents.analysis.requested_outcomes import anchored_requirements, parse_requirements
from src.domains.agents.services.outcome_directive import _pipeline_observations
from src.domains.agents.services.outcome_evidence import GoalCoverage, requested_outcome_coverage
from src.domains.psyche.constants import EfficacyDomain
from src.domains.psyche.efficacy_contracts import EfficacyObservation

FIELD_EFFICACY = "psyche_efficacy"
_SUBJECTIVE = frozenset(
    {EfficacyDomain.CREATIVITY, EfficacyDomain.EMOTIONAL_SUPPORT, EfficacyDomain.SOCIAL}
)


def observations_from_coverage(
    domains: tuple[EfficacyDomain, ...], coverage: Sequence[GoalCoverage]
) -> tuple[EfficacyObservation, ...]:
    """A global receipt cannot reward two domains or judge a subjective outcome."""
    if len(domains) != 1 or not coverage or domains[0] in _SUBJECTIVE:
        return tuple(
            EfficacyObservation(domain=domain, verdict="unknown", reason="insufficient_evidence")
            for domain in domains
        )
    statuses = {item.status for item in coverage}
    if statuses == {"satisfied"}:
        verdict, reason = "success", "goal_satisfied"
    elif "pending_confirmation" in statuses:
        verdict, reason = "excluded", "human_decision"
    elif "partial" in statuses or "satisfied" in statuses:
        verdict, reason = "partial", "incomplete_coverage"
    else:
        # failed has no cause attribution; provider/auth/quota/opaque are neutral.
        verdict, reason = "unknown", "insufficient_evidence"
    return (EfficacyObservation(domain=domains[0], verdict=verdict, reason=reason),)


def current_coverage(state: Mapping[str, object]) -> tuple[GoalCoverage, ...]:
    qi = state.get("query_intelligence")
    if not isinstance(qi, Mapping):
        return ()
    query, domains = qi.get("original_query"), qi.get("domains")
    if not isinstance(query, str) or not isinstance(domains, list):
        return ()
    requirements = anchored_requirements(
        parse_requirements(qi.get("requested_outcomes")), query, domains, trusted_checkpoint=True
    )
    evidence = state.get("requested_outcome_evidence") or _pipeline_observations(state)
    if not isinstance(evidence, list):
        return ()
    timezone = state.get("user_timezone")
    return requested_outcome_coverage(
        requirements, evidence, timezone=timezone if isinstance(timezone, str) else "UTC"
    )


class EfficacyCapture:
    """Only accept a server-stamped QI for this logical run (including HITL resume)."""

    def __init__(self) -> None:
        self.context: EfficacyTurnContext | None = None
        self._state: dict[str, object] = {}

    def update(self, chunk: Mapping[str, object], *, run_id: str) -> None:
        qi = chunk.get("query_intelligence")
        if not isinstance(qi, Mapping):
            return
        context = read_turn_context(qi.get("efficacy_context"))
        if context is None or context.run_id != run_id:
            return
        self.context = context
        self._state = {
            key: chunk[key]
            for key in (
                "query_intelligence",
                "requested_outcome_evidence",
                "completed_steps",
                "execution_plan",
                "user_timezone",
            )
            if key in chunk
        }

    def envelope(self, *, run_id: str) -> dict[str, object]:
        if (
            self.context is None
            or self.context.run_id != run_id
            or not self.context.collection_enabled
        ):
            return {}
        observations = observations_from_coverage(
            self.context.analysis.domains, current_coverage(self._state)
        )
        return {
            FIELD_EFFICACY: {
                "version": 1,
                "context": self.context.model_dump(mode="json"),
                "observations": [item.model_dump(mode="json") for item in observations],
            }
        }
