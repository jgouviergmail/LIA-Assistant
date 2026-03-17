"""
LangChain v1 tool for sub-agent delegation.

Single tool: delegate_to_sub_agent_tool — creates an ephemeral expert
sub-agent and executes it through the full LIA graph.

Architecture:
- The planner decides autonomously when to delegate (complex, specialized tasks)
- The tool creates an ephemeral SubAgent record (tracking), builds a system
  prompt with the expertise directive, and executes via stream_chat_response()
- Multiple delegates with no depends_on run in PARALLEL (wave-based executor)
- Sub-agents are read-only (blocked_tools enforced)
- Depth limit: sub-agents cannot spawn sub-sub-agents (session_id prefix check)

Push-based, ephemeral, orchestrated delegation pattern.

Phase: F6 — Persistent Specialized Sub-Agents
"""

from typing import Annotated

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool

from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    handle_tool_exception,
    parse_user_id,
    validate_runtime_config,
)
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

# Agent name for metrics
_AGENT_NAME = "sub_agent_tools"


@tool
@track_tool_metrics(
    tool_name="delegate_to_sub_agent",
    agent_name=_AGENT_NAME,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def delegate_to_sub_agent_tool(
    expertise: Annotated[
        str,
        "Domain expertise of the sub-agent to create "
        "(e.g., 'expert comptable', 'specialiste transport ferroviaire')",
    ],
    instruction: Annotated[
        str,
        "Detailed task instruction with all necessary context " "and expected output format",
    ],
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Delegate a task to a specialized ephemeral sub-agent.

    Creates a temporary expert sub-agent with the given expertise and
    executes it through the full LIA pipeline. The sub-agent has access
    to search, fetch, and analysis tools but CANNOT perform write
    operations (send email, create event, etc.).

    Use this for tasks requiring deep domain expertise, parallel research,
    or specialized analysis. The sub-agent works independently and returns
    its complete analysis.

    IMPORTANT:
    - Sub-agents are READ-ONLY (no mutations, no HITL operations)
    - Multiple delegates with no depends_on run in PARALLEL
    - Reference results via $steps.step_N.analysis in subsequent steps
    - Handle HITL operations (send_email, etc.) YOURSELF after sub-agent results

    Args:
        expertise: Role description for the sub-agent specialist.
        instruction: Detailed task with context and expected output.
        runtime: Tool runtime (injected).

    Returns:
        Sub-agent analysis result in structured_data["analysis"].
    """
    config = validate_runtime_config(runtime, "delegate_to_sub_agent_tool")
    if isinstance(config, UnifiedToolOutput):
        return config

    try:
        # Depth check: prevent sub-agent from spawning sub-sub-agents
        if config.session_id and config.session_id.startswith("subagent_"):
            return UnifiedToolOutput.failure(
                message="Sub-agents cannot delegate to other sub-agents " "(depth limit reached).",
                error_code="DEPTH_LIMIT_EXCEEDED",
            )

        user_id = parse_user_id(config.user_id)

        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            # Check user preference (within same DB session)
            from src.domains.users.service import UserService

            user_service = UserService(db)
            user_obj = await user_service.get_user_by_id(user_id)
            if user_obj and not getattr(user_obj, "sub_agents_enabled", True):
                return UnifiedToolOutput.failure(
                    message="Sub-agents are disabled in your preferences. "
                    "Enable them in Settings to use this feature.",
                    error_code="FEATURE_DISABLED",
                )

            # Preventive cleanup: delete stale ephemeral sub-agents
            # from previous runs to avoid hitting per-user limit
            from src.domains.sub_agents.repository import SubAgentRepository

            repo = SubAgentRepository(db)
            stale_ephemerals = await repo.get_all_for_user(user_id, include_disabled=True)
            for sa in stale_ephemerals:
                if sa.name.startswith("ephemeral_") and sa.status != "executing":
                    await repo.delete(sa)
            await db.flush()
            from src.domains.sub_agents.constants import (
                SUBAGENT_DEFAULT_BLOCKED_TOOLS,
            )
            from src.domains.sub_agents.executor import SubAgentExecutor
            from src.domains.sub_agents.models import SubAgentCreatedBy
            from src.domains.sub_agents.schemas import SubAgentCreate
            from src.domains.sub_agents.service import SubAgentService

            service = SubAgentService(db)

            # Create ephemeral sub-agent record (tracking + audit)
            # UUID suffix ensures uniqueness for parallel delegates
            from uuid import uuid4

            unique_suffix = uuid4().hex[:8]
            subagent_data = SubAgentCreate(
                name=f"ephemeral_{expertise[:40]}_{unique_suffix}",
                description=f"Ephemeral expert: {expertise[:100]}",
                system_prompt=expertise,
                blocked_tools=SUBAGENT_DEFAULT_BLOCKED_TOOLS,
            )
            subagent = await service.create(
                user_id=user_id,
                data=subagent_data,
                created_by=SubAgentCreatedBy.ASSISTANT.value,
            )
            await db.commit()

            # Execute via full graph
            executor = SubAgentExecutor()

            from src.domains.agents.tools.runtime_helpers import (
                get_user_preferences,
            )

            user_timezone, user_language, _ = await get_user_preferences(runtime)

            result = await executor.execute(
                subagent=subagent,
                instruction=instruction,
                user_id=user_id,
                user_timezone=user_timezone,
                user_language=user_language,
                db=db,
            )

            # Record result then cleanup ephemeral sub-agent
            _MAX_SUMMARY_LENGTH = 200
            summary = (
                result.result[:_MAX_SUMMARY_LENGTH] + "..."
                if result.result and len(result.result) > _MAX_SUMMARY_LENGTH
                else result.result or ""
            )

            # Delete ephemeral sub-agent (avoid hitting per-user limit)
            # Use repo.delete directly (bypasses status check)
            await repo.delete(subagent)
            await db.commit()

            # Consolidate sub-agent tokens AND costs into parent TrackingContext.
            # Sub-agents are isolated (direct pipeline, no conversation).
            # Their tokens are in separate MessageTokenSummary rows.
            # We inject them into the parent tracker so the user sees
            # the real total cost in their chat bubble.
            if result.session_id:
                try:
                    from src.core.context import current_tracker
                    from src.domains.chat.models import MessageTokenSummary

                    parent_tracker = current_tracker.get()
                    if parent_tracker:
                        from decimal import Decimal

                        from sqlalchemy import select

                        from src.infrastructure.cache.pricing_cache import (
                            get_cached_usd_eur_rate,
                        )

                        stmt = (
                            select(MessageTokenSummary)
                            .where(MessageTokenSummary.session_id == result.session_id)
                            .limit(1)
                        )
                        sa_summary = (await db.execute(stmt)).scalar_one_or_none()

                        if sa_summary and sa_summary.total_prompt_tokens > 0:
                            # Pass real costs from sub-agent summary
                            # instead of model_name="subagent" (which
                            # the pricing cache doesn't recognize → cost=0).
                            sa_cost_eur = float(sa_summary.total_cost_eur or 0)
                            rate = Decimal(str(get_cached_usd_eur_rate()))
                            sa_cost_usd = (
                                float(sa_summary.total_cost_eur / rate) if rate > 0 else 0.0
                            )

                            await parent_tracker.record_node_tokens(
                                node_name=f"subagent:{expertise[:30]}",
                                model_name="subagent-aggregate",
                                prompt_tokens=(sa_summary.total_prompt_tokens),
                                completion_tokens=(sa_summary.total_completion_tokens),
                                cached_tokens=(sa_summary.total_cached_tokens),
                                cost_usd=sa_cost_usd,
                                cost_eur=sa_cost_eur,
                                usd_to_eur_rate=rate,
                                duration_ms=(result.duration_seconds * 1000),
                            )
                except Exception as consolidation_err:
                    # Must not break execution, but log for debuggability
                    import structlog

                    structlog.get_logger(__name__).warning(
                        "subagent_token_consolidation_failed",
                        expertise=expertise[:30],
                        error=f"{type(consolidation_err).__name__}: {consolidation_err}",
                    )

            if not result.success:
                return UnifiedToolOutput.failure(
                    message=(f"Sub-agent '{expertise}' failed: {result.error}"),
                    error_code="EXECUTION_FAILED",
                    metadata={
                        "expertise": expertise,
                        "duration_seconds": result.duration_seconds,
                    },
                )

            return UnifiedToolOutput.action_success(
                message=summary,
                structured_data={
                    "analysis": result.result or "",
                    "expertise": expertise,
                    "type": "sub_agent_analysis",
                },
                metadata={
                    "expertise": expertise,
                    "duration_seconds": result.duration_seconds,
                    "tokens_used": result.tokens_used,
                },
            )

    except Exception as e:
        return handle_tool_exception(
            e,
            "delegate_to_sub_agent_tool",
            {"expertise": expertise, "instruction": instruction[:100]},
        )
