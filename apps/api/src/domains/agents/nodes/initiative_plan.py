"""Initiative actions → execution plan (validation, dedup, plan build).

Extracted from ``initiative_node`` (file-size ratchet — a logical file never
grows): the deterministic guards between the LLM decision and the parallel
executor. One-way dependency: ``initiative_node`` imports these helpers; the
``InitiativeAction`` schema stays with its ``InitiativeDecision`` parent and
is only type-imported here (no runtime cycle).
"""

from __future__ import annotations

import json
from contextlib import suppress
from typing import TYPE_CHECKING, Any

import structlog

from src.domains.agents.context.runtime_context import runtime_user_id_str
from src.domains.agents.orchestration.plan_schemas import parameters_to_dict

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from src.domains.agents.nodes.initiative_node import InitiativeAction

logger = structlog.get_logger(__name__)


def _validate_read_only(
    actions: list[InitiativeAction],
    read_only_manifests: list[Any],
) -> list[InitiativeAction]:
    """Defense in depth: reject non-read-only tools and exact duplicates.

    The LLM occasionally emits the same (tool, parameters) action twice in a
    single decision (observed 2026-07-22: two identical weather checks for
    co-located events) — executing both wastes a paid provider call whenever
    the target tool has no response cache.
    """
    from src.infrastructure.observability.metrics_agents import (
        initiative_actions_rejected_total,
    )

    allowed_names = {m.name for m in read_only_manifests}
    validated = []
    seen: set[str] = set()
    for action in actions:
        if action.tool_name not in allowed_names:
            logger.warning(
                "initiative_action_rejected_non_readonly",
                tool_name=action.tool_name,
            )
            # Metrics are best-effort — never break the validation.
            with suppress(Exception):
                initiative_actions_rejected_total.labels(reason="non_readonly").inc()
            continue
        params = json.dumps(parameters_to_dict(action.parameters), sort_keys=True, default=str)
        key = f"{action.tool_name}|{params}"
        if key in seen:
            logger.info("initiative_action_deduplicated", tool_name=action.tool_name)
            # Metrics are best-effort — never break the validation.
            with suppress(Exception):
                initiative_actions_rejected_total.labels(reason="duplicate").inc()
            continue
        seen.add(key)
        validated.append(action)
    return validated


def _build_initiative_plan(
    actions: list[InitiativeAction],
    config: RunnableConfig,
) -> Any:
    """Build an ExecutionPlan from validated initiative actions."""
    from src.core.context import get_request_tool_manifests
    from src.domains.agents.orchestration.plan_schemas import (
        ExecutionPlan,
        ExecutionStep,
        StepType,
    )

    user_id = runtime_user_id_str("unknown")
    manifests = get_request_tool_manifests()
    manifest_by_name = {m.name: m for m in manifests}
    steps = []
    for i, action in enumerate(actions):
        manifest = manifest_by_name.get(action.tool_name)
        agent_name = manifest.agent if manifest else "unknown_agent"

        steps.append(
            ExecutionStep(
                step_id=f"initiative_{i}",
                step_type=StepType.TOOL,
                agent_name=agent_name,
                tool_name=action.tool_name,
                parameters=parameters_to_dict(action.parameters),
                description=action.rationale,
            )
        )
    return ExecutionPlan(user_id=str(user_id), steps=steps, execution_mode="parallel")
