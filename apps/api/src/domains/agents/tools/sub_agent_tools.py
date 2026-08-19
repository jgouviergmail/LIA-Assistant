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
    - tools    = full registry, filtered to a read-only subset
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
gated by the global `SUB_AGENTS_ENABLED` flag.
"""

from typing import Annotated, Any

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool

from src.core.config import get_settings
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.react_runner import ReactSubAgentRunner
from src.domains.agents.tools.runtime_helpers import (
    handle_tool_exception,
    validate_runtime_config,
)
from src.domains.agents.tools.tool_registry import get_all_tools
from src.domains.sub_agents.constants import SUBAGENT_DEFAULT_BLOCKED_TOOLS
from src.domains.sub_agents.skill_resolver import resolve_tools_for_subagent
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

# Agent name for metrics
_AGENT_NAME = "sub_agent_tools"

# Truncation length for the message field of the success UnifiedToolOutput
# (the full text is preserved in structured_data["analysis"]).
_MAX_SUMMARY_LENGTH = 200


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
        "Detailed task statement for the sub-agent. Do NOT paste raw data — "
        "the sub-agent has its own read-only tools and fetches what it needs. "
        "Resolved $ref payloads exceeding the configured cap are rejected.",
    ],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Delegate a UNITARY expert task to an ephemeral sub-agent (ReAct loop).

    The sub-agent runs a single scoped ReAct loop over a read-only toolset,
    with a tight `recursion_limit`, and returns its final analytical text.
    Multiple delegates with no `depends_on` run in PARALLEL.

    IMPORTANT:
    - Sub-agents are READ-ONLY (no mutations, no HITL operations).
    - Reference results via `$steps.step_N.analysis` in subsequent steps.
    - Handle mutations (send_email, etc.) YOURSELF after sub-agent results.

    Args:
        expertise: Specialist role / directives (becomes the sub-agent persona).
        instruction: Task statement (NOT raw data — the sub-agent fetches its own).
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
        # toggle (Option B) was removed — the global `SUB_AGENTS_ENABLED` flag
        # gates the whole subsystem (planner catalogue + this tool's
        # registration) at startup. No need for a per-call DB lookup.

        # Build the read-only toolset for the sub-agent.
        # `resolve_tools_for_subagent` filters out write tools AND excludes
        # `delegate_to_sub_agent_tool` itself (primary anti-recursion).
        # The whitelist (Settings) keeps the sub-agent focused on factual
        # research instead of exploring the full ~80-tool catalogue — which
        # would otherwise burn the ReAct recursion_limit without converging.
        all_tools_dict = get_all_tools()
        read_only_tools = resolve_tools_for_subagent(
            allowed_tools=get_settings().subagent_research_tools_whitelist_parsed,
            blocked_tools=SUBAGENT_DEFAULT_BLOCKED_TOOLS,
            all_tools=list(all_tools_dict.values()),
        )

        # Run the scoped ReAct loop via the existing generic runner
        # (same machinery as browser_task_tool / mcp_server_task_tool).
        runner = ReactSubAgentRunner("subagent", "subagent_react_prompt")
        react_result = await runner.run(
            task=instruction,
            tools=read_only_tools,
            prompt_vars={"expertise": expertise},
            parent_runtime=runtime,
            thread_prefix="subagent",
            recursion_limit=get_settings().subagent_default_max_iterations,
            display_name=f"sub-agent: {expertise[:40]}",
        )

        # Map the ReactSubAgentResult to a UnifiedToolOutput.
        final = react_result.final_message or ""
        if final.startswith("Error:"):
            return UnifiedToolOutput.failure(
                message=(f"Sub-agent '{expertise[:60]}' did not complete: {final[:300]}"),
                error_code="EXECUTION_FAILED",
                metadata={
                    "expertise": expertise,
                    "duration_ms": react_result.duration_ms,
                    "iteration_count": react_result.iteration_count,
                },
            )

        summary = final[:_MAX_SUMMARY_LENGTH] + "..." if len(final) > _MAX_SUMMARY_LENGTH else final

        return UnifiedToolOutput.action_success(
            message=summary,
            structured_data={
                "analysis": final,
                "expertise": expertise,
                "type": "sub_agent_analysis",
            },
            metadata={
                "expertise": expertise,
                "duration_ms": react_result.duration_ms,
                "iteration_count": react_result.iteration_count,
            },
        )

    except Exception as e:
        return handle_tool_exception(
            e,
            "delegate_to_sub_agent_tool",
            {"expertise": expertise, "instruction": instruction[:100]},
        )
