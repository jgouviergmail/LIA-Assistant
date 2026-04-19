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
from src.core.llm_config_helper import get_llm_config_for_agent
from src.core.time_utils import get_prompt_datetime_formatted
from src.domains.agents.constants import (
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_CURRENT_TURN_ID,
    STATE_KEY_EXECUTION_PLAN,
)
from src.domains.agents.models import MessagesState
from src.domains.agents.orchestration.plan_schemas import ParameterItem, parameters_to_dict
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.structured_output import get_structured_output
from src.infrastructure.observability.decorators import track_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_node_duration_seconds,
    agent_node_executions_total,
)
from src.infrastructure.observability.tracing import trace_node

logger = structlog.get_logger(__name__)

# Fields to exclude from payload extraction (internal/technical, not useful for LLM)
_EXCLUDE_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "etag",
        "kind",
        "selfLink",
        "iCalUID",
        "htmlLink",
        "creator",
        "organizer",
        "metadata",
        "raw",
        "_raw",
        "meta",
        "_meta",
        "index",
        "_index",
        "resourceName",
        "status",
        "colorId",
        "reminders",
        "sequence",
        "updated",
        "created",
        "photos",
        "coverPhotos",
        "memberships",
        "sources",
        "objectType",
        "polyline",
        "encoded_polyline",
        "steps",
    }
)

# Parameters with non-obvious values that need inline descriptions in initiative prompts
_NEEDS_DESCRIPTION: frozenset[str] = frozenset(
    {
        "travel_mode",
        "units",
        "date",
        "user_message",
        "fields",
    }
)


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

    tool_name: str = Field(description="Exact tool name from available tools")
    parameters: list[ParameterItem] = Field(
        default_factory=list,
        description="Tool parameters as name/value pairs",
    )
    rationale: str = Field(description="Why this adds concrete value (one sentence)")


class InitiativeDecision(BaseModel):
    """LLM decision for the initiative phase."""

    model_config = ConfigDict(extra="forbid")

    analysis: str = Field(description="Actionable signals found (one sentence)")
    should_act: bool = Field(description="True only if high-value cross-domain action found")
    reasoning: str = Field(description="Why acting or not (one sentence)")
    actions: list[InitiativeAction] = Field(
        default_factory=list,
        description="Read-only actions (empty if should_act=false)",
    )
    suggestion: str | None = Field(
        default=None,
        description="Question for user when a write action would help but is not allowed here",
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
    from src.domains.agents.registry.catalogue import is_initiative_eligible
    from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

    # Collect CROSS-DOMAIN targets: domains ADJACENT to executed ones but NOT
    # the executed domains themselves. The initiative's purpose is to check OTHER
    # domains for implications — re-checking executed domains wastes tokens and
    # produces low-value actions (data already in execution_summary).
    executed_set = set(executed_domains)
    target_domains: set[str] = set()
    # Forward: related domains of executed ones
    for domain_name in executed_domains:
        config = DOMAIN_REGISTRY.get(domain_name)
        if config:
            target_domains.update(config.related_domains)
    # Reverse: domains that declare executed ones as related
    for domain_name, config in DOMAIN_REGISTRY.items():
        if any(ed in config.related_domains for ed in executed_domains):
            target_domains.add(domain_name)
    # Exclude already-executed domains (cross-domain only)
    target_domains -= executed_set

    manifests = get_request_tool_manifests()

    def _extract_domain(m: Any) -> str:
        if hasattr(m, "agent") and m.agent:
            return m.agent.removesuffix("_agent")
        return "unknown"

    return [
        m for m in manifests if is_initiative_eligible(m) and _extract_domain(m) in target_domains
    ]


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
    current_turn_id: int | None = None,
) -> str:
    """Format execution results for initiative LLM evaluation.

    Combines agent_results (status + tool summaries) with registry data
    (actual structured content like weather details, event names, contact
    info). The registry is the primary source of rich data when tools use
    registry_enabled=True (step_results only contain short summaries).

    Args:
        agent_results: Dict of composite_key → AgentResult-like dicts.
        registry: Current turn registry items (RegistryItem dicts).
        current_turn_id: Current turn ID to filter agent_results by turn.

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

            # Generic extraction: iterate all payload fields, exclude technical ones
            summary_parts: list[str] = []
            for key, val in payload.items():
                if key in _EXCLUDE_FIELDS or key.startswith("_"):
                    continue
                if val is None:
                    continue
                if isinstance(val, str):
                    if len(val) > 150:
                        val = val[:150] + "…"
                    summary_parts.append(f"{key}: {val}")
                elif isinstance(val, (int, float, bool)):
                    summary_parts.append(f"{key}: {val}")
                elif isinstance(val, list) and val:
                    # Compact list preview (e.g., attendees, names)
                    preview = str(val[0])[:80]
                    if len(val) > 1:
                        preview += f" (+{len(val) - 1} more)"
                    summary_parts.append(f"{key}: {preview}")
                # Skip dicts and other complex types to keep summary concise

            if summary_parts:
                sections.append(f"[{domain}] {'; '.join(summary_parts[:8])}")

    # 2. Fallback: extract from agent_results step_results if registry is empty
    # FIX 2026-04-08: Filter by current_turn_id to prevent stale data from
    # previous turns leaking into the initiative prompt. agent_results keys
    # are prefixed with turn_id (e.g., "2:plan_executor").
    if not sections and agent_results:
        filtered_results = agent_results
        if current_turn_id is not None:
            turn_prefix = f"{current_turn_id}:"
            filtered_results = {k: v for k, v in agent_results.items() if k.startswith(turn_prefix)}

        for _composite_key, result_data in filtered_results.items():
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
    """Format initiative-eligible tool manifests in compact format.

    Uses one line per tool with description and key parameters inline.
    Non-obvious parameters (enums, special behaviors) keep their descriptions;
    obvious ones (query, max_results, location) are listed by name only.
    This reduces token consumption by ~70% vs the full parameter format.
    """
    lines = []
    for m in manifests:
        # Build compact param list
        param_parts = []
        for p in m.parameters:
            if p.name in _NEEDS_DESCRIPTION and p.description:
                # Keep description for non-obvious params
                param_parts.append(f"{p.name}: {p.description}")
            elif p.required:
                param_parts.append(f"{p.name} (required)")
            else:
                param_parts.append(p.name)
        params_str = f" | Params: {', '.join(param_parts)}" if param_parts else ""
        lines.append(f"- {m.name}: {m.description}{params_str}")
    return "\n".join(lines)


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

    # ── 1b. Skip after HITL resolution (accept/refuse) ──────────────
    # When the user just approved or refused a draft, disambiguation, or tool
    # confirmation, running initiative is pointless — the user already made an
    # explicit decision. The result keys are set by hitl_dispatch_node and
    # cleared later by response_node, so their presence reliably indicates
    # "we just came from a HITL interaction".
    if (
        state.get("draft_action_result")
        or state.get("entity_disambiguation_result")
        or state.get("tool_confirmation_result")
    ):
        logger.info("initiative_skipped", reason="hitl_just_resolved", run_id=run_id)
        return {STATE_KEY_INITIATIVE_SKIPPED_REASON: "hitl_just_resolved"}

    iteration = state.get(STATE_KEY_INITIATIVE_ITERATION, 0)

    # ── 1c. Skip when a skill is driving the turn ───────────────────
    # Skills define their own deterministic output scope (plan_template +
    # references). Running initiative on top injects orthogonal domains
    # (e.g. "nearby places" during a daily briefing) that pollute the
    # skill's intended output contract and confuse the response LLM which
    # must follow the skill's formatting instructions verbatim.
    execution_plan = state.get(STATE_KEY_EXECUTION_PLAN)
    active_skill_name = (
        execution_plan.metadata.get("skill_name")
        if execution_plan is not None and getattr(execution_plan, "metadata", None)
        else None
    )
    if active_skill_name:
        logger.info(
            "initiative_skipped",
            reason="skill_active",
            skill_name=active_skill_name,
            run_id=run_id,
        )
        return {
            STATE_KEY_INITIATIVE_SKIPPED_REASON: "skill_active",
            STATE_KEY_INITIATIVE_ITERATION: iteration + 1,
        }

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
    current_turn_id = state.get(STATE_KEY_CURRENT_TURN_ID)
    current_registry = state.get("current_turn_registry") or state.get("registry") or {}
    execution_summary = _format_execution_summary(
        agent_results, registry=current_registry, current_turn_id=current_turn_id
    )
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
    agent_config = get_llm_config_for_agent(settings, NODE_INITIATIVE)
    provider = agent_config.provider

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

    try:
        decision = await asyncio.wait_for(
            get_structured_output(
                llm=llm,
                messages=[HumanMessage(content=prompt)],
                schema=InitiativeDecision,
                provider=provider,
                node_name=NODE_INITIATIVE,
                config=config,
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
            "registry_ids": list(par_result.registry.keys()),
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
