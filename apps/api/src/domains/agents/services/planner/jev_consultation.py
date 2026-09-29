"""Select an exact, fixed consultation after the normal authorized catalogue filter."""

from time import perf_counter
from typing import cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from pydantic import JsonValue

from src.core.context import get_request_tool_manifests
from src.core.run_config import run_id_of
from src.core.time_utils import now_utc
from src.domains.agents.analysis.query_intelligence import QueryIntelligence
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.registry.catalogue import get_tool_category, manifest_allows_mode
from src.domains.agents.services.planner.consultation_paths import (
    READ_PATHS,
    ReadPath,
    consultation_question,
)
from src.domains.agents.services.planner.planner_utils import build_plan_from_steps
from src.domains.agents.services.planner.planning_result import PlanningResult
from src.domains.agents.services.smart_catalogue_service import FilteredCatalogue
from src.domains.llm_config.jev_registry import JevUsage
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.jev_debug_store import record_action
from src.infrastructure.llm.jev_runtime import choose_with_jev
from src.infrastructure.observability.metrics_jev import (
    jev_decision_duration_seconds,
    jev_decisions_total,
)

MIN_CONFIDENCE = 0.99


def eligible_query(qi: QueryIntelligence, *, bounded: bool = False) -> bool:
    return (
        qi.immediate_intent == "search"
        and qi.confidence >= 0.9
        and qi.immediate_confidence >= 0.9
        and not qi.is_mutation_intent
        and len(qi.domains) == 1
        and qi.primary_domain in qi.domains
        and qi.turn_type == "ACTION"
        and (bounded or not qi.has_temporal_reference)
        and not _has_dependencies(qi)
        and bool(qi.english_query.strip())
    )


def _has_dependencies(qi: QueryIntelligence) -> bool:
    return bool(
        qi.resolved_context
        or qi.resolved_references
        or qi.for_each_detected
        or qi.has_cardinality_risk
        or qi.detected_skill_name
    )


def _accepted_path(
    attempt: DecisionAttempt,
    paths: dict[str, ReadPath],
    threshold: float,
) -> ReadPath | None:
    answer = attempt.answer
    if attempt.outcome != "success" or answer is None or answer.confidence < threshold:
        return None
    return paths.get(answer.choice)


async def _record_outcome(
    owner: UUID,
    attempt: DecisionAttempt,
    selected: ReadPath | None,
    usage: JevUsage,
    started: float,
) -> None:
    outcome = (
        "selected"
        if selected
        else ("uncertain" if attempt.outcome == "success" else attempt.outcome)
    )
    await record_action(
        owner,
        attempt.diagnostic,
        action="selected" if selected else "fallback",
        outcome=outcome,
        target=selected.tool if selected else "planner",
    )
    jev_decisions_total.labels(usage=usage, outcome=outcome).inc()
    jev_decision_duration_seconds.labels(usage=usage, outcome=outcome).observe(
        perf_counter() - started
    )


def available_paths(
    qi: QueryIntelligence,
    catalogue: FilteredCatalogue,
    candidates: dict[str, ReadPath] | None = None,
) -> dict[str, ReadPath]:
    filtered = set(catalogue.get_tool_names())
    allowed = {
        manifest.name: manifest
        for manifest in get_request_tool_manifests()
        if manifest.name in filtered
        and manifest_allows_mode(manifest, "pipeline")
        and not manifest.permissions.hitl_required
        and (
            manifest.mutation_policy == "read"
            or (manifest.mutation_policy is None and get_tool_category(manifest) == "search")
        )
    }
    return {
        key: value
        for key, value in (READ_PATHS if candidates is None else candidates).items()
        if value.domain == qi.primary_domain and value.tool in allowed
    }


async def try_consultation_plan(
    intelligence: QueryIntelligence,
    config: RunnableConfig,
    catalogue: FilteredCatalogue,
    *,
    journal_context: str,
) -> PlanningResult | None:
    context = runtime_context_if_running()
    from src.domains.agents.services.planner.jev_bounded_consultation import (
        BOUNDED_MIN_CONFIDENCE,
        bounded_paths,
        bounded_question,
        wants_bounded_path,
    )

    bounded = wants_bounded_path(intelligence)
    if context is None or not eligible_query(intelligence, bounded=bounded):
        return None
    anchor = now_utc()
    candidates = bounded_paths(intelligence, context.timezone, anchor) if bounded else None
    paths = available_paths(intelligence, catalogue, candidates)
    if not paths:
        return None
    question = bounded_question(paths) if bounded else consultation_question(paths)
    usage = JevUsage.CONSULTATION_BOUNDED if bounded else JevUsage.CONSULTATION_PATH
    started = perf_counter()
    attempt = await choose_with_jev(
        usage=usage,
        user_id=context.user_id,
        run_id=run_id_of(config, "unknown"),
        state=cast(
            JsonValue,
            {
                "intelligence": intelligence.to_serializable_dict(),
                "journal_context": journal_context,
                "date_anchor": anchor.isoformat(),
                "timezone": context.timezone,
                "candidates": {
                    key: {"tool": value.tool, "parameters": dict(value.parameters)}
                    for key, value in paths.items()
                },
            },
        ),
        question=question,
    )
    answer = attempt.answer
    selected = _accepted_path(attempt, paths, BOUNDED_MIN_CONFIDENCE if bounded else MIN_CONFIDENCE)
    await _record_outcome(context.user_id, attempt, selected, usage, started)
    if selected is None:
        return None
    # Reuse the same plan type and validators as generated plans. No execution or
    # approval is performed here; every parameter comes from a reviewed constant.
    from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType

    plan = build_plan_from_steps(
        [
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name=f"{selected.domain}_agent",
                tool_name=selected.tool,
                parameters=dict(selected.parameters),
                depends_on=[],
            )
        ],
        intelligence,
        config,
    )
    assert answer is not None
    plan.metadata["jev_path"] = answer.choice
    return PlanningResult(plan=plan, success=True, used_template=True, filtered_catalogue=catalogue)
