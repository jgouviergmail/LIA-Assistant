"""Started reads remain observable when a final answer omits their failures."""

from __future__ import annotations

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.domains.agents.analysis.query_intelligence_helpers import get_qi_attr
from src.domains.agents.analysis.requested_outcomes import (
    GoalRequirement,
    anchored_requirements,
    parse_requirements,
)
from src.domains.agents.models import MessagesState
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.outcome_evidence import (
    GoalCoverage,
    coverage_has_gap,
    requested_outcome_coverage,
)


def requested_requirements(state: MessagesState) -> tuple[GoalRequirement, ...]:
    """Only literal, current-request anchors become obligations."""
    requirements = parse_requirements(get_qi_attr(state, "requested_outcomes", default=()))
    query: object = get_qi_attr(state, "original_query", default="")
    domains: object = get_qi_attr(state, "domains", default=[])
    if not isinstance(query, str) or not isinstance(domains, list):
        return ()
    return anchored_requirements(
        requirements,
        query,
        [domain for domain in domains if isinstance(domain, str)],
        trusted_checkpoint=True,
    )


def requested_coverage(state: MessagesState) -> tuple[GoalCoverage, ...]:
    return requested_outcome_coverage(
        requested_requirements(state),
        state.get("requested_outcome_evidence") or [],
        timezone=state.get("user_timezone") or DEFAULT_USER_DISPLAY_TIMEZONE,
    )


def requested_outcome_block(state: MessagesState) -> str | None:
    """A versioned directive exposes proven coverage on every model call."""
    coverage = requested_coverage(state)
    if not coverage:
        return None
    return load_prompt("requested_outcome_directive").format(
        coverage="\n".join(f"- {item.requirement.label}: {item.status}" for item in coverage)
    )


def requested_final_report(state: MessagesState) -> dict[str, object]:
    coverage = requested_coverage(state)
    if not coverage:
        return {}
    return {"requested_outcomes": [item.model_dump(mode="json") for item in coverage]}


def proven_final_content(state: MessagesState, content: object) -> str:
    """A known missing result uses the response's factual synthesis path."""
    coverage = requested_coverage(state)
    if any(coverage_has_gap(item) for item in coverage):
        return ""
    return content if isinstance(content, str) else ""


def observed_gaps(state: MessagesState) -> tuple[str, ...]:
    """The gaps the code observed, which a final answer may have left unsaid.

    A requested goal left missing, failed, or partial when the request demanded
    completeness (``requested_coverage``); and a started read that FAILED. A read
    the tool cut at its cap — ``truncated``, a next page — is NOT a gap: it
    answered what it was asked and the cut is stated to the model (ADR-286).
    Counted as one, it forced a recovery pass the model could not resolve on
    every agenda or mail question whose list outgrew the cap — measured
    2026-10-12: 4 dev turns of 4, 21 production turns of 65, 14 of them
    fruitless, two model calls and 10 to 15 s each. An empty read can answer a
    question.
    """
    observations = state.get("react_read_observations") or {}
    coverage = requested_coverage(state)
    goal_gaps = tuple(
        f"{item.requirement.label}: {item.status}" for item in coverage if coverage_has_gap(item)
    )
    started_gaps = tuple(
        f"{observation['tool_name']}: started read returned {observation['outcome']} "
        f"(observation {signature[:12]})"
        for signature, observation in observations.items()
        if observation["outcome"] == "failed"
    )
    return (*goal_gaps, *started_gaps)


def observed_recovery_outcome(state: MessagesState, outcome: str | None) -> str | None:
    """Removing the model's declaration is not evidence that a failed read recovered."""
    if outcome != "resolved" or not observed_gaps(state):
        return outcome
    return "still_unresolved"
