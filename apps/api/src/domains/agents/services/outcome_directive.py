"""Expose factual requested-result gaps to final response synthesis."""

import json
from collections.abc import Mapping

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.domains.agents.analysis.requested_outcomes import anchored_requirements, parse_requirements
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.outcome_evidence import (
    observe_requested_outcome,
    requested_outcome_coverage,
)


def _step_field(step: object, key: str) -> object:
    return step.get(key) if isinstance(step, Mapping) else getattr(step, key, None)


def _pipeline_observations(state: Mapping[str, object]) -> list[dict[str, object]]:
    """Read canonical completed outputs; no provider success is manufactured."""
    completed = state.get("completed_steps")
    steps = _step_field(state.get("execution_plan"), "steps")
    if not isinstance(completed, Mapping) or not isinstance(steps, list):
        return []
    observations: list[dict[str, object]] = []
    for step in steps:
        name = _step_field(step, "tool_name")
        step_id = _step_field(step, "step_id")
        if not isinstance(name, str) or not isinstance(step_id, str):
            continue
        data = completed.get(step_id)
        if not isinstance(data, dict):
            continue
        observation = observe_requested_outcome(
            name, {}, {"structured_data": data, "success": data.get("success")}
        )
        if observation is not None:
            observations.append(observation)
    return observations


def build_requested_outcomes_block(state: Mapping[str, object]) -> str:
    """Never infer successful external execution from a pending draft or prose."""
    intelligence = state.get("query_intelligence")
    if not isinstance(intelligence, Mapping):
        return ""
    requirements = parse_requirements(intelligence.get("requested_outcomes"))
    query = intelligence.get("original_query")
    domains = intelligence.get("domains")
    if not isinstance(query, str) or not isinstance(domains, list):
        return ""
    requirements = anchored_requirements(requirements, query, domains, trusted_checkpoint=True)
    if not requirements:
        return ""
    timezone = state.get("user_timezone")
    coverage = requested_outcome_coverage(
        requirements,
        state.get("requested_outcome_evidence") or _pipeline_observations(state),
        timezone=timezone if isinstance(timezone, str) else DEFAULT_USER_DISPLAY_TIMEZONE,
    )
    return str(load_prompt("requested_outcomes_directive")).format(
        coverage=json.dumps([item.model_dump(mode="json") for item in coverage], ensure_ascii=False)
    )
