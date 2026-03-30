"""
Initiative Node — Post-execution proactive enrichment.

Evaluates execution results and decides whether read-only complementary
actions would meaningfully enrich the response. 100% prompt-driven.

The node follows this flow:
1. Feature flag + iteration budget checks (instant short-circuit)
2. Structural pre-filter: are adjacent read-only tools available?
3. Memory + interests loading (parallel, for user-aware decisions)
4. LLM evaluation (structured output: actions + optional suggestion)
5. Read-only validation (defense in depth)
6. Execution via execute_plan_parallel (reuse existing infrastructure)
7. State merge (agent_results, registry, suggestion)

As a native LangGraph node, token tracking and debug panel attribution
are handled automatically via the graph's callbacks and
``enrich_config_with_node_metadata``. No manual consolidation needed.

Phase: ADR-062 — Agent Initiative Phase + MCP Iterative Support
Created: 2026-03-24
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, Field

from src.core.config import settings
from src.core.constants import (
    INITIATIVE_INTERESTS_LIMIT,
    INITIATIVE_LLM_TIMEOUT_SECONDS,
    INITIATIVE_MEMORY_LIMIT,
    INITIATIVE_MEMORY_MIN_SCORE,
    NODE_INITIATIVE,
    STATE_KEY_INITIATIVE_ITERATION,
    STATE_KEY_INITIATIVE_RESULTS,
    STATE_KEY_INITIATIVE_SKIPPED_REASON,
    STATE_KEY_INITIATIVE_SUGGESTION,
)
from src.core.time_utils import get_prompt_datetime_formatted
from src.domains.agents.constants import STATE_KEY_AGENT_RESULTS, STATE_KEY_CURRENT_TURN_ID
from src.domains.agents.models import MessagesState
from src.domains.agents.orchestration.plan_schemas import ParameterItem, parameters_to_dict
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata
from src.infrastructure.observability.decorators import track_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_node_duration_seconds,
    agent_node_executions_total,
)
from src.infrastructure.observability.tracing import trace_node

logger = structlog.get_logger(__name__)


# =============================================================================
# Pydantic Schemas (Structured Output)
# =============================================================================


class InitiativeAction(BaseModel):
    """A single read-only complementary action.

    Uses ``list[ParameterItem]`` for parameters (same pattern as
    ``ExecutionStepLLM``) to ensure OpenAI strict mode compatibility.
    ``dict[str, Any]`` is not allowed in strict JSON schema.
    """

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(description="Exact tool name from the available tools list")
    parameters: list[ParameterItem] = Field(
        default_factory=list,
        description="Tool parameters as a list of name/value pairs",
    )
    rationale: str = Field(
        description="Why this action adds concrete value to the response (one sentence)"
    )


class InitiativeDecision(BaseModel):
    """LLM decision for the initiative phase."""

    model_config = ConfigDict(extra="forbid")

    analysis: str = Field(
        description="Brief analysis of actionable signals found in results (2-3 sentences)"
    )
    should_act: bool = Field(
        description="True only if at least one HIGH VALUE read-only action was identified"
    )
    reasoning: str = Field(description="Why acting or not acting (one sentence)")
    actions: list[InitiativeAction] = Field(
        default_factory=list,
        description="Read-only actions to execute (empty if should_act=false)",
    )
    suggestion: str | None = Field(
        default=None,
        description=(
            "Proactive suggestion when a WRITE action would be valuable but "
            "cannot be executed (read-only phase). Phrased as a question for the user. "
            "Example: 'Would you like me to create a calendar event for Thursday 2pm?'"
        ),
    )


# =============================================================================
# Helpers
# =============================================================================


def _extract_run_id(config: RunnableConfig) -> str:
    """Extract run_id from RunnableConfig metadata."""
    metadata = config.get("metadata") or {}
    return metadata.get("run_id", "unknown")


def _extract_domains(state: MessagesState) -> list[str]:
    """Extract domain names from QueryIntelligence in state.

    Handles both dataclass (runtime) and dict (checkpoint restoration) formats.
    """
    qi = state.get("query_intelligence")
    if qi is None:
        return []
    # Dataclass: attribute access
    domains = getattr(qi, "domains", None)
    # Dict fallback (checkpoint serialization)
    if domains is None and isinstance(qi, dict):
        domains = qi.get("domains")
    return domains if isinstance(domains, list) else []


def _extract_original_query(state: MessagesState) -> str:
    """Extract the user's original query from state messages."""
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) and isinstance(msg.content, str):
            return msg.content
    return ""


def _get_adjacent_read_only_manifests(
    executed_domains: list[str],
) -> list[Any]:
    """Get read-only tools from domains adjacent to execution results.

    Uses DomainConfig.related_domains to find adjacent domains,
    then filters for read-only tools only. This is a structural
    pre-filter (capability check), not a semantic decision.

    Args:
        executed_domains: Domains that were used in the execution plan.

    Returns:
        Read-only tool manifests from adjacent domains.
    """
    from src.core.context import get_request_tool_manifests
    from src.domains.agents.registry.catalogue import is_read_only_tool
    from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

    # Collect executed domains + their related domains (forward)
    # + domains that declare executed domains as related (reverse)
    target_domains: set[str] = set()
    for domain_name in executed_domains:
        target_domains.add(domain_name)
        config = DOMAIN_REGISTRY.get(domain_name)
        if config:
            target_domains.update(config.related_domains)
    # Reverse: if weather declares event as related, and event was executed,
    # weather becomes adjacent (bidirectional adjacency for initiative)
    for domain_name, config in DOMAIN_REGISTRY.items():
        if any(ed in config.related_domains for ed in executed_domains):
            target_domains.add(domain_name)

    manifests = get_request_tool_manifests()

    def _extract_domain(m: Any) -> str:
        if hasattr(m, "agent") and m.agent:
            return m.agent.removesuffix("_agent")
        return "unknown"

    return [m for m in manifests if is_read_only_tool(m) and _extract_domain(m) in target_domains]


def _validate_read_only(
    actions: list[InitiativeAction],
    read_only_manifests: list[Any],
) -> list[InitiativeAction]:
    """Defense in depth: reject any action targeting a non-read-only tool."""
    allowed_names = {m.name for m in read_only_manifests}
    validated = []
    for action in actions:
        if action.tool_name in allowed_names:
            validated.append(action)
        else:
            logger.warning(
                "initiative_action_rejected_non_readonly",
                tool_name=action.tool_name,
            )
    return validated


async def _load_memory_facts(
    user_id: str,
    execution_summary: str,
) -> list[str] | None:
    """Load semantically relevant memory facts for initiative context."""
    if not user_id:
        return None
    try:
        from src.domains.agents.middleware.memory_injection import get_memory_facts_for_query

        return await get_memory_facts_for_query(
            user_id=user_id,
            query=execution_summary,
            limit=INITIATIVE_MEMORY_LIMIT,
            min_score=INITIATIVE_MEMORY_MIN_SCORE,
        )
    except Exception as exc:
        logger.warning("initiative_memory_load_failed", error=str(exc))
        return None


async def _load_user_interests(user_id: str) -> dict[str, Any]:
    """Load user interest profile for initiative context."""
    try:
        from src.domains.interests.services import get_user_interests_for_debug

        return await get_user_interests_for_debug(user_id)
    except Exception:
        return {"interests": [], "enabled": False}


def _format_memory_facts(facts: list[str] | None) -> str:
    """Format memory facts for prompt injection."""
    if not facts:
        return "No relevant memories."
    return "Relevant user context:\n" + "\n".join(f"- {f}" for f in facts)


def _format_interests(profile: dict[str, Any]) -> str:
    """Format user interests for prompt injection."""
    interests = profile.get("interests", [])
    active = [
        f"{i['topic']} ({i['category']})"
        for i in interests[:INITIATIVE_INTERESTS_LIMIT]
        if i.get("status") == "active"
    ]
    if not active:
        return "No known interests."
    return "User interests: " + ", ".join(active)


def _format_execution_summary(
    agent_results: dict[str, Any],
    registry: dict[str, Any] | None = None,
) -> str:
    """Format execution results for initiative LLM evaluation.

    Combines agent_results (status + tool summaries) with registry data
    (actual structured content like weather details, event names, contact
    info). The registry is the primary source of rich data when tools use
    registry_enabled=True (step_results only contain short summaries).

    Args:
        agent_results: Dict of composite_key → AgentResult-like dicts.
        registry: Current turn registry items (RegistryItem dicts).

    Returns:
        Human-readable summary with enough detail for cross-domain reasoning.
    """
    sections: list[str] = []

    # 1. Extract from registry (rich data: weather details, event names, etc.)
    if registry:
        for _item_id, item in registry.items():
            if not isinstance(item, dict):
                continue
            payload = item.get("payload", {})
            meta = item.get("meta", {})
            domain = meta.get("domain", "unknown")

            # Build a concise summary from payload fields
            # Different domains have different payload structures
            summary_parts: list[str] = []
            for key in (
                "summary",
                "title",
                "name",
                "description",
                "location",
                "snippet",
                "query",
                "answer",
                "content",
            ):
                val = payload.get(key)
                if val and isinstance(val, str):
                    summary_parts.append(f"{key}: {val[:150]}")
            # Weather-specific fields
            for key in (
                "temperature",
                "temp_min",
                "temp_max",
                "weather_description",
                "humidity",
                "wind_speed",
                "rain",
                "date",
            ):
                val = payload.get(key)
                if val is not None:
                    summary_parts.append(f"{key}: {val}")
            # Event-specific fields
            for key in ("start_datetime", "end_datetime", "attendees"):
                val = payload.get(key)
                if val is not None:
                    summary_parts.append(f"{key}: {str(val)[:100]}")

            if summary_parts:
                sections.append(f"[{domain}] {'; '.join(summary_parts[:8])}")

    # 2. Fallback: extract from agent_results step_results if registry is empty
    if not sections and agent_results:
        for _composite_key, result_data in agent_results.items():
            if not isinstance(result_data, dict):
                continue
            status = result_data.get("status", "unknown")
            agent_name = result_data.get("agent_name", "agent")

            if status == "success":
                data = result_data.get("data", {})
                if isinstance(data, dict):
                    step_results = data.get("step_results") or data.get("aggregated_results") or []
                    for sr in step_results[:5] if isinstance(step_results, list) else []:
                        if isinstance(sr, dict):
                            tool = sr.get("tool_name", "tool")
                            sr_result = sr.get("result", {})
                            if isinstance(sr_result, dict):
                                summary = (
                                    sr_result.get("message", "")
                                    or sr_result.get("result", "")
                                    or str(sr_result)[:200]
                                )
                            else:
                                summary = str(sr_result)[:200]
                            if summary:
                                sections.append(f"[{tool}] {summary}")
            elif status in ("failed", "error"):
                error = result_data.get("error", "Unknown error")
                sections.append(f"[{agent_name}] ERROR: {error}")

    return "\n".join(sections) if sections else "No execution results."


def _format_tools_for_prompt(manifests: list[Any]) -> str:
    """Format read-only tool manifests for initiative prompt."""
    sections = []
    for m in manifests:
        params = []
        for p in m.parameters:
            req = "required" if p.required else "optional"
            params.append(f"  - {p.name} ({p.type}, {req}): {p.description}")
        params_str = "\n".join(params) if params else "  (no parameters)"
        sections.append(f"Tool: {m.name}\nDescription: {m.description}\nParameters:\n{params_str}")
    return "\n\n".join(sections)


def _build_initiative_plan(
    actions: list[InitiativeAction],
    config: RunnableConfig,
) -> Any:
    """Build an ExecutionPlan from validated initiative actions."""
    from src.core.context import get_request_tool_manifests
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType

    user_id = (config.get("configurable") or {}).get("user_id", "unknown")
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


# =============================================================================
# Node
# =============================================================================


@trace_node(NODE_INITIATIVE)
@track_metrics(
    node_name=NODE_INITIATIVE,
    duration_metric=agent_node_duration_seconds,
    counter_metric=agent_node_executions_total,
)
async def initiative_node(
    state: MessagesState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Evaluate execution results and optionally enrich with read-only actions.

    Args:
        state: Current graph state with execution results.
        config: RunnableConfig with user_id, thread_id, store, callbacks.

    Returns:
        State update dict. Empty dict = pass-through (zero impact).
    """
    # ── 1. Feature flag ──────────────────────────────────────────────
    if not settings.initiative_enabled:
        return {}

    run_id = _extract_run_id(config)
    iteration = state.get(STATE_KEY_INITIATIVE_ITERATION, 0)

    # ── 2. Iteration budget ──────────────────────────────────────────
    if iteration >= settings.initiative_max_iterations:
        logger.info("initiative_skipped", reason="max_iterations", run_id=run_id)
        return {STATE_KEY_INITIATIVE_SKIPPED_REASON: "max_iterations_reached"}

    # ── 3. Extract executed domains from query_intelligence ──────────
    executed_domains = _extract_domains(state)

    # ── 4. Structural pre-filter: adjacent read-only tools exist? ────
    adjacent_manifests = _get_adjacent_read_only_manifests(executed_domains)
    logger.info(
        "initiative_prefilter",
        executed_domains=executed_domains,
        adjacent_tool_count=len(adjacent_manifests),
        run_id=run_id,
    )
    if not adjacent_manifests:
        return {
            STATE_KEY_INITIATIVE_SKIPPED_REASON: "no_adjacent_read_only_tools",
            STATE_KEY_INITIATIVE_ITERATION: iteration + 1,
        }

    # ── 5. Load user context (memory + interests) in parallel ────────
    user_id = (config.get("configurable") or {}).get("user_id", "")
    user_language = state.get("user_language", "fr")
    user_timezone = state.get("user_timezone", "UTC")

    agent_results = state.get(STATE_KEY_AGENT_RESULTS, {})
    current_registry = state.get("current_turn_registry") or state.get("registry") or {}
    execution_summary = _format_execution_summary(agent_results, registry=current_registry)
    original_query = _extract_original_query(state)

    memory_facts, interest_profile = await asyncio.gather(
        _load_memory_facts(str(user_id), execution_summary),
        _load_user_interests(str(user_id)),
    )

    # ── 6. Build prompt and call initiative LLM ──────────────────────
    tools_description = _format_tools_for_prompt(adjacent_manifests)
    memory_text = _format_memory_facts(memory_facts)
    interests_text = _format_interests(interest_profile)

    llm = get_llm(NODE_INITIATIVE)
    structured_llm = llm.with_structured_output(InitiativeDecision)
    prompt = load_prompt("initiative_prompt", version="v1").format(
        execution_summary=execution_summary,
        available_tools=tools_description,
        memory_facts=memory_text,
        user_interests=interests_text,
        user_language=user_language,
        user_timezone=user_timezone,
        original_query=original_query,
        current_datetime=get_prompt_datetime_formatted(),
        max_actions=settings.initiative_max_actions,
    )

    enriched_config = enrich_config_with_node_metadata(config, NODE_INITIATIVE)

    try:
        decision = await asyncio.wait_for(
            structured_llm.ainvoke(
                [HumanMessage(content=prompt)],
                config=enriched_config,
            ),
            timeout=INITIATIVE_LLM_TIMEOUT_SECONDS,
        )
    except (TimeoutError, Exception) as exc:
        logger.warning("initiative_llm_failed", error=str(exc), run_id=run_id)
        return {STATE_KEY_INITIATIVE_ITERATION: iteration + 1}

    logger.info(
        "initiative_decision",
        should_act=decision.should_act,
        action_count=len(decision.actions),
        has_suggestion=decision.suggestion is not None,
        reasoning=decision.reasoning,
        run_id=run_id,
    )

    # ── 7. Collect suggestion (even if should_act=False) ─────────────
    state_update: dict[str, Any] = {
        STATE_KEY_INITIATIVE_ITERATION: iteration + 1,
    }
    if decision.suggestion:
        state_update[STATE_KEY_INITIATIVE_SUGGESTION] = decision.suggestion

    # ── 8. If no actions → return with suggestion only ───────────────
    if not decision.should_act or not decision.actions:
        state_update[STATE_KEY_INITIATIVE_SKIPPED_REASON] = decision.reasoning
        return state_update

    # ── 9. Validate read-only (defense in depth) ─────────────────────
    validated_actions = _validate_read_only(decision.actions, adjacent_manifests)
    if not validated_actions:
        logger.warning("initiative_all_actions_rejected", run_id=run_id)
        state_update[STATE_KEY_INITIATIVE_SKIPPED_REASON] = "all_actions_non_readonly"
        return state_update

    # ── 10. Build and execute plan ───────────────────────────────────
    from src.domains.agents.orchestration.mappers import map_execution_result_to_agent_result
    from src.domains.agents.orchestration.parallel_executor import execute_plan_parallel
    from src.domains.agents.orchestration.schemas import ExecutionResult
    from src.domains.agents.orchestration.schemas import StepResult as LegacyStepResult
    from src.domains.agents.utils.state_cleanup import cleanup_dict_by_turn_id

    logger.info(
        "initiative_executing",
        action_count=len(validated_actions),
        tool_names=[a.tool_name for a in validated_actions],
        run_id=run_id,
    )
    plan = _build_initiative_plan(validated_actions, config)
    par_result = await execute_plan_parallel(
        execution_plan=plan,
        config=config,
        run_id=f"initiative_{run_id}",
        initial_registry=state.get("registry"),
        turn_id=state.get(STATE_KEY_CURRENT_TURN_ID),
    )

    # ── 11. Convert ParallelExecutionResult → ExecutionResult for mapper ─
    # Same conversion as task_orchestrator_node (lines 1424-1464)
    legacy_step_results = []
    for idx, step in enumerate(plan.steps):
        if step.step_id in par_result.completed_steps:
            step_data = par_result.completed_steps[step.step_id]
            legacy_step_results.append(
                LegacyStepResult(
                    step_index=idx,
                    tool_name=step.tool_name or step.step_id,
                    args=step.parameters or {},
                    result=step_data if isinstance(step_data, dict) else {"data": step_data},
                    success=(
                        step_data.get("success", True) if isinstance(step_data, dict) else True
                    ),
                    error=step_data.get("error") if isinstance(step_data, dict) else None,
                )
            )
    execution_result = ExecutionResult(
        success=all(sr.success for sr in legacy_step_results) if legacy_step_results else True,
        step_results=legacy_step_results,
        total_steps=len(plan.steps),
        completed_steps=len(par_result.completed_steps),
    )

    turn_id = state.get(STATE_KEY_CURRENT_TURN_ID, 0)
    new_agent_results = map_execution_result_to_agent_result(
        execution_result=execution_result,
        plan_id=plan.plan_id,
        turn_id=turn_id,
        data_registry=par_result.registry,
    )

    # Rename composite keys to avoid collision with task_orchestrator results.
    # map_execution_result_to_agent_result uses "plan_executor" as agent name,
    # which would overwrite the original execution results.
    from src.domains.agents.orchestration.mappers import make_agent_result_key

    # Re-key under "initiative" to avoid collision with task_orchestrator's "plan_executor"
    initiative_key = make_agent_result_key(turn_id, NODE_INITIATIVE)
    renamed_results: dict[str, Any] = (
        {initiative_key: next(iter(new_agent_results.values()))} if new_agent_results else {}
    )

    state_update[STATE_KEY_AGENT_RESULTS] = cleanup_dict_by_turn_id(
        {**state.get(STATE_KEY_AGENT_RESULTS, {}), **renamed_results},
        max_results=settings.max_agent_results,
        label="agent_results",
    )

    # registry: merge_registry reducer handles merge
    state_update["registry"] = par_result.registry
    # current_turn_registry: NO reducer → explicit merge
    existing_ctr = state.get("current_turn_registry") or {}
    state_update["current_turn_registry"] = {**existing_ctr, **par_result.registry}

    # ── 12. Store initiative results for debug panel ─────────────────
    initiative_results = list(state.get(STATE_KEY_INITIATIVE_RESULTS, []))
    initiative_results.append(
        {
            "iteration": iteration,
            "reasoning": decision.reasoning,
            "actions_executed": len(validated_actions),
            "actions": [a.model_dump() for a in validated_actions],
            "suggestion": decision.suggestion,
        }
    )
    state_update[STATE_KEY_INITIATIVE_RESULTS] = initiative_results

    logger.info(
        "initiative_completed",
        actions_executed=len(validated_actions),
        registry_items=len(par_result.registry),
        has_suggestion=decision.suggestion is not None,
        run_id=run_id,
    )
    return state_update
