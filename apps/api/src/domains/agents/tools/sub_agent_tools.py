"""
LangChain v1 tool for sub-agent delegation.

Single tool: delegate_to_sub_agent_tool — runs a scoped expert ReAct loop
via the generic ReactSubAgentRunner (ADR-083).

Architecture (ADR-083 — Sub-Agent Delegation as Parameterized ReAct Loop):
- The planner decides autonomously when to delegate (H1: an expert persona
  must produce a MATERIALLY BETTER answer than the assistant directly).
- This tool DOES NOT spin up a bespoke mini-pipeline anymore (no
  query_analyzer / SmartPlannerService / synthesis chain). Instead it
  instantiates the generic ReactSubAgentRunner with:
    - llm_type = "subagent"
    - prompt   = "subagent_react_prompt" (expertise persona + read-only rules)
    - tools    = what the delegating turn's catalogue offers (``_offered_by_the_turn``),
                 narrowed to the research whitelist and a read-only subset
    - recursion_limit = settings.subagent_default_max_iterations
- Multiple delegates with no depends_on still run in PARALLEL (wave-based
  executor at the parent level).
- Sub-agents are READ-ONLY (blocked_tools enforced via resolve_tools_for_subagent).
- Depth limit: a sub-agent cannot spawn a sub-sub-agent. Two guards:
    1. resolve_tools_for_subagent excludes delegate_to_sub_agent_tool itself
       (primary anti-recursion mechanism).
    2. This function rejects calls when the inbound session_id starts with
       "subagent_" (belt-and-suspenders).

Token attribution flows automatically into the parent TokenTrackingCallback
via metadata["node_name_override"] = "sub-agent: <expertise>" (set by the
runner). No separate MessageTokenSummary, no manual consolidation.

After ADR-083 Phase 2 cleanup, this is the ONLY sub-agent execution path
in the codebase. The bespoke SubAgentExecutor pipeline, the /sub-agents REST
API, the sub_agents DB table, and the per-user `sub_agents_enabled` toggle
were all removed (no UI consumer, no real usage). The whole subsystem is
gated by the global `SUB_AGENTS_ENABLED` flag and, at call time, by the
operator's capability switch.
"""

from typing import Annotated, Any

from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, InjectedToolArg, tool

from src.core.config import get_settings
from src.core.context import request_tool_manifests_ctx
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.effects.runtime import resolve_policy
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.react_runner import (
    ReactSubAgentRunner,
    SubAgentOutcome,
    failure_code_of,
    failure_sentence,
    partial_fields,
)
from src.domains.agents.tools.react_runner_budget import tool_rounds_for
from src.domains.agents.tools.runtime_helpers import (
    handle_tool_exception,
    validate_runtime_config,
)
from src.domains.agents.tools.tool_registry import get_all_tools
from src.domains.sub_agents.constants import SUBAGENT_DEFAULT_BLOCKED_TOOLS
from src.domains.sub_agents.instruction_contract import instruction_description
from src.domains.sub_agents.skill_resolver import resolve_tools_for_subagent
from src.infrastructure.llm.providers.token_counter import EstimationTokenCounter
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

# Agent name for metrics
_AGENT_NAME = "sub_agent_tools"

# Truncation length for the message field of the success UnifiedToolOutput
# (the full text is preserved in structured_data["analysis"]).
_MAX_SUMMARY_LENGTH = 200

logger = get_logger(__name__)


def _oversized_instruction(instruction: str) -> UnifiedToolOutput | None:
    """The refusal of an instruction above the configured token cap, if it is.

    Args:
        instruction: The instruction as the tool received it.

    Returns:
        An ``INVALID_INPUT`` failure naming the estimate and the cap, or None.
    """
    cap = get_settings().subagent_instruction_max_tokens_resolved
    token_estimate = EstimationTokenCounter().count(instruction, model="any")
    if token_estimate <= cap:
        return None
    logger.warning("subagent_instruction_oversized", token_estimate=token_estimate, cap=cap)
    return UnifiedToolOutput.failure(
        message=(
            f"Sub-agent instruction too large ({token_estimate} tokens > cap {cap}). "
            "State the task and the facts the expert needs — the relevant fields, "
            "not whole payloads."
        ),
        error_code="INVALID_INPUT",
    )


async def _offered_by_the_turn(tools: list[BaseTool]) -> list[BaseTool]:
    """The tools of ``tools`` the delegating turn itself offers.

    A sub-agent holds nothing its turn does not: the turn's catalogue already
    withholds a switched-off capability, an unconnected provider and an
    application operation the account may not run — read from the global
    registry instead, the default research tools searched the web after an
    operator switched web search off. Outside a turn (no catalogue published)
    the capability switches still hold.

    Args:
        tools: Candidate tool instances.

    Returns:
        Those the turn offers.
    """
    catalogue = request_tool_manifests_ctx.get()
    if catalogue is not None:
        offered = {manifest.name for manifest in catalogue}
        return [candidate for candidate in tools if candidate.name in offered]
    from src.domains.agents.registry import get_global_registry
    from src.domains.agents.services.planner_capability_filter import (
        tools_hidden_by_capabilities,
    )

    hidden = await tools_hidden_by_capabilities(get_global_registry())
    return [candidate for candidate in tools if candidate.name not in hidden]


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
        "(e.g., 'chartered accountant', 'rail transport specialist')",
    ],
    # The facts the planner's manifest states too (point 38): the loop binds
    # this schema, never the manifest, so the cap is stated here.
    instruction: Annotated[str, instruction_description(in_plan=False)],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Delegate a UNITARY expert task to an ephemeral sub-agent (ReAct loop).

    The sub-agent runs a single scoped ReAct loop over a read-only toolset,
    with a tight `recursion_limit`, and returns its final analytical text.
    Multiple delegates with no `depends_on` run in PARALLEL.

    IMPORTANT:
    - Sub-agents are READ-ONLY (no mutations, no HITL operations).
    - Its analysis comes back as this tool's result.
    - Handle mutations (send_email, etc.) YOURSELF after sub-agent results.

    Args:
        expertise: Specialist role / directives (becomes the sub-agent persona).
        instruction: Task statement and the facts the expert needs, under the cap.
        runtime: Tool runtime (injected by LangChain).

    Returns:
        UnifiedToolOutput with the sub-agent's text in `structured_data["analysis"]`.
    """
    config = validate_runtime_config(runtime, "delegate_to_sub_agent_tool")
    if isinstance(config, UnifiedToolOutput):
        return config

    try:
        # Depth check (belt-and-suspenders): the primary anti-recursion is in
        # resolve_tools_for_subagent, which excludes this tool from a sub-agent's
        # toolset. This guard catches legacy or odd invocation paths.
        if config.session_id and config.session_id.startswith("subagent_"):
            return UnifiedToolOutput.failure(
                message="Sub-agents cannot delegate to other sub-agents (depth limit reached).",
                error_code="DEPTH_LIMIT_EXCEEDED",
            )

        # ADR-083 Phase 2 cleanup: the per-user `sub_agents_enabled` preference
        # toggle (Option B) was removed. The global flag gates the subsystem at
        # STARTUP (planner catalogue + this tool's registration); since B7 the
        # operator's switch is read HERE, at call time, because a switch flipped
        # after boot must take effect without a restart.
        from src.domains.feature_switches.registry import (
            PlatformCapability,
            is_capability_enabled,
        )

        if not await is_capability_enabled(PlatformCapability.SUB_AGENTS):
            return UnifiedToolOutput.failure(
                message="Sub-agent delegation is disabled on this instance.",
                error_code="CONFIGURATION_ERROR",
            )

        # The cap the description states, enforced HERE so it holds in both
        # modes: in a plan the references are resolved by now, and a ReAct
        # loop writes the instruction itself (point 38).
        oversized = _oversized_instruction(instruction)
        if oversized is not None:
            return oversized

        # Build the read-only toolset for the sub-agent.
        # `resolve_tools_for_subagent` filters out write tools AND excludes
        # `delegate_to_sub_agent_tool` itself (primary anti-recursion).
        # The whitelist (Settings) keeps the sub-agent focused on factual
        # research instead of exploring the full ~80-tool catalogue — which
        # would otherwise burn the ReAct recursion_limit without converging.
        read_only_tools = resolve_tools_for_subagent(
            allowed_tools=get_settings().subagent_research_tools_whitelist_parsed,
            blocked_tools=SUBAGENT_DEFAULT_BLOCKED_TOOLS,
            all_tools=await _offered_by_the_turn(list(get_all_tools().values())),
            # ADR-263: the read-only guarantee stops being a hand list. The
            # reader is injected because ``sub_agents`` must not import back
            # into ``agents`` (F009 runtime-cycle ratchet).
            policy_of=resolve_policy,
        )

        # Run the scoped ReAct loop via the existing generic runner
        # (same machinery as browser_task_tool / mcp_server_task_tool).
        recursion_limit = get_settings().subagent_default_max_iterations
        runner = ReactSubAgentRunner("subagent", "subagent_react_prompt")
        react_result = await runner.run(
            task=instruction,
            tools=read_only_tools,
            prompt_vars={
                "expertise": expertise,
                # What the loop holds, read from what runs: the tools it is bound to
                # (after the read-only filter, not the raw whitelist) and the budget
                # the runner enforces — a prompt states what the code holds (ADR-284).
                "research_tools": ", ".join(tool.name for tool in read_only_tools) or "none",
                "max_tool_rounds": str(tool_rounds_for(recursion_limit)),
            },
            parent_runtime=runtime,
            thread_prefix="subagent",
            recursion_limit=recursion_limit,
            display_name=f"sub-agent: {expertise[:40]}",
        )

        # Map the ReactSubAgentResult to a UnifiedToolOutput: the outcome decides,
        # never the text (ADR-303). A closed or cut analysis is still an analysis;
        # what it lacks travels in its own fields.
        run_metadata = {
            "expertise": expertise,
            "duration_ms": react_result.duration_ms,
            "iteration_count": react_result.iteration_count,
        }
        if react_result.outcome is not SubAgentOutcome.ANSWERED:
            return UnifiedToolOutput.failure(
                message=f"Sub-agent '{expertise[:60]}' {failure_sentence(react_result)}.",
                error_code=failure_code_of(react_result),
                metadata=run_metadata,
            )

        final = react_result.final_message
        summary = final[:_MAX_SUMMARY_LENGTH] + "..." if len(final) > _MAX_SUMMARY_LENGTH else final

        return UnifiedToolOutput.action_success(
            message=summary,
            structured_data={
                "analysis": final,
                "expertise": expertise,
                "type": "sub_agent_analysis",
                **partial_fields(react_result),
            },
            metadata=run_metadata,
        )

    except Exception as e:
        return handle_tool_exception(
            e,
            "delegate_to_sub_agent_tool",
            {"expertise": expertise, "instruction": instruction[:100]},
        )
