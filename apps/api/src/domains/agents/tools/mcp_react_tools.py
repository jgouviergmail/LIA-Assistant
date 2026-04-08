"""
MCP ReAct Tools — Iterative MCP interaction via ReAct sub-agent.

When an MCP server is configured with ``iterative_mode=true``, the planner sees
a single ``mcp_server_task`` tool instead of individual server tools. This tool
launches a ReAct agent that interacts with the server iteratively:

1. If a documentation tool exists (e.g., read_me), call it first
2. Plan the approach based on documentation or tool descriptions
3. Execute tools in logical order with error recovery

The ``_MCPReActWrapper`` converts ``UnifiedToolOutput`` to string for the ReAct LLM
while accumulating registry items (e.g., MCP App HTML widgets) for propagation
back to the parent graph.

Supports both admin MCP (``mcp_server_task_tool``) and per-user MCP
(``mcp_user_server_task_tool``) servers.

Phase: ADR-062 — Agent Initiative Phase + MCP Iterative Support
Created: 2026-03-24
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, InjectedToolArg, tool
from pydantic import PrivateAttr

from src.core.config import settings
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.react_runner import ReactSubAgentRunner
from src.domains.agents.tools.tool_registry import get_all_tools
from src.domains.agents.utils.rate_limiting import rate_limit
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = structlog.get_logger(__name__)

_AGENT_NAME = "mcp_react"


# =============================================================================
# MCP ReAct Wrapper — String output + registry capture for ReAct loop
# =============================================================================


class _MCPReActWrapper(BaseTool):
    """Wrapper that converts MCP tool adapter output to string for ReAct LLM.

    The ReAct agent needs string results to reason about tool outputs.
    MCPToolAdapter/UserMCPToolAdapter return UnifiedToolOutput (rich object
    with registry items).

    This wrapper:
    - Returns ``result.message`` (string) to the ReAct LLM
    - Accumulates all ``registry_updates`` (e.g., MCP App HTML widgets) in a
      PrivateAttr for later propagation to the parent graph
    - Exposes the original tool's ``args_schema`` for correct tool calling
    - Uses the short MCP tool name (``create_view``, not ``mcp_excalidraw_create_view``)
    """

    _inner: MCPToolAdapter | UserMCPToolAdapter = PrivateAttr()
    _accumulated_registry: dict[str, Any] = PrivateAttr(default_factory=dict)

    def __init__(self, inner: MCPToolAdapter | UserMCPToolAdapter) -> None:
        """Initialize wrapper from an MCPToolAdapter or UserMCPToolAdapter.

        Args:
            inner: The original MCP tool adapter to wrap.
        """
        super().__init__(
            name=inner.mcp_tool_name,
            description=inner.description,
            args_schema=inner.args_schema,
        )
        self._inner = inner

    async def _arun(self, **kwargs: Any) -> str:
        """Execute the inner MCP tool and return string result.

        Captures registry items (MCP App widgets, etc.) in _accumulated_registry
        for later collection by ReactSubAgentRunner.

        Errors are caught and returned as string messages so the ReAct agent
        can reason about them and retry with corrected parameters.

        Args:
            **kwargs: Tool arguments.

        Returns:
            String representation of the tool result for ReAct LLM context.
        """
        try:
            result = await self._inner._arun(**kwargs)
        except BaseException as exc:
            # Return error as string so the ReAct agent can reason and retry
            # instead of crashing the entire sub-agent loop.
            error_msg = str(exc)
            # ExceptionGroup nests the real error — extract it
            if hasattr(exc, "exceptions"):
                for sub in exc.exceptions:
                    if hasattr(sub, "exceptions"):
                        for inner in sub.exceptions:
                            error_msg = str(inner)
                    else:
                        error_msg = str(sub)
            logger.warning(
                "mcp_react_wrapper_tool_error",
                tool_name=self.name,
                error=error_msg,
                error_type=type(exc).__name__,
            )
            return f"ERROR: {error_msg}"

        # Capture registry items (MCP App HTML, etc.)
        if hasattr(result, "registry_updates") and result.registry_updates:
            self._accumulated_registry.update(result.registry_updates)

        # Return string for ReAct LLM
        if hasattr(result, "message"):
            return result.message
        return str(result)

    def _run(self, **kwargs: Any) -> str:
        """MCP tools are async only."""
        raise NotImplementedError("MCP ReAct wrapper is async only.")


# =============================================================================
# Helpers
# =============================================================================


def _get_mcp_server_tools_for_react(server_name: str) -> list[_MCPReActWrapper]:
    """Get MCP tools wrapped for ReAct consumption.

    Filters the central tool registry for tools matching the
    ``mcp_{server_name}_*`` naming convention and wraps them.

    Args:
        server_name: MCP server name (e.g., "excalidraw").

    Returns:
        List of _MCPReActWrapper instances with short tool names.
    """
    prefix = f"mcp_{server_name}_"
    all_tools = get_all_tools()
    react_tools: list[_MCPReActWrapper] = []
    for name, tool_instance in all_tools.items():
        if name.startswith(prefix) and isinstance(tool_instance, MCPToolAdapter):
            react_tools.append(_MCPReActWrapper(tool_instance))
    return react_tools


def _get_user_mcp_server_tools_for_react(server_id_prefix: str) -> list[_MCPReActWrapper]:
    """Get user MCP tools from ContextVar, wrapped for ReAct consumption.

    Filters the per-request UserMCPToolsContext for tools matching the
    ``mcp_user_{server_id_prefix}_*`` naming convention and wraps them.

    Args:
        server_id_prefix: First 8 chars of the server UUID.

    Returns:
        List of _MCPReActWrapper instances with short tool names.
    """
    from src.core.context import user_mcp_tools_ctx

    user_ctx = user_mcp_tools_ctx.get()
    if not user_ctx:
        return []

    prefix = f"mcp_user_{server_id_prefix}_"
    react_tools: list[_MCPReActWrapper] = []
    for name, tool_instance in user_ctx.tool_instances.items():
        if name.startswith(prefix) and isinstance(tool_instance, UserMCPToolAdapter):
            react_tools.append(_MCPReActWrapper(tool_instance))
    return react_tools


# =============================================================================
# Shared ReAct execution logic
# =============================================================================


def _has_mcp_app_tools(server_tools: list[_MCPReActWrapper]) -> bool:
    """Check if any tool in the list has an MCP App resource URI.

    MCP App servers expose interactive HTML widgets (e.g., Excalidraw diagrams).
    They benefit from a more capable LLM for the ReAct loop.

    Args:
        server_tools: Wrapped MCP tools to check.

    Returns:
        True if at least one tool has an app_resource_uri.
    """
    return any(getattr(tool._inner, "app_resource_uri", None) for tool in server_tools)


async def _run_mcp_react_task(
    server_tools: list[_MCPReActWrapper],
    server_name: str,
    task: str,
    thread_prefix: str,
    runtime: ToolRuntime | None,
    extra_structured_data: dict[str, Any] | None = None,
) -> UnifiedToolOutput:
    """Run a ReAct agent on a set of MCP tools.

    Shared core logic for both admin and user MCP iterative task tools.
    Automatically selects a more capable LLM for MCP App servers (those with
    interactive HTML widgets like Excalidraw).

    Args:
        server_tools: Wrapped MCP tools for the ReAct agent.
        server_name: Human-readable server name (for prompt and display).
        task: Natural language task description.
        thread_prefix: Unique prefix for the ReAct thread.
        runtime: Parent ToolRuntime for callback propagation.
        extra_structured_data: Additional fields for structured_data output.

    Returns:
        UnifiedToolOutput with ReAct result and accumulated registry items.
    """
    # MCP App servers (with interactive widgets) use a dedicated, more capable LLM
    llm_type = "mcp_app_react_agent" if _has_mcp_app_tools(server_tools) else "mcp_react_agent"
    runner = ReactSubAgentRunner(llm_type, "mcp_react_agent_prompt")
    react_result = await runner.run(
        task=task,
        tools=server_tools,
        prompt_vars={"server_name": server_name},
        parent_runtime=runtime,
        thread_prefix=thread_prefix,
        recursion_limit=settings.mcp_react_max_iterations,
        display_name=f"MCP Iterative: {server_name}",
    )

    structured_data: dict[str, Any] = {
        "server_name": server_name,
        "task": task,
        "iterations": react_result.iteration_count,
        "duration_ms": react_result.duration_ms,
    }
    if extra_structured_data:
        structured_data.update(extra_structured_data)

    return UnifiedToolOutput.data_success(
        message=react_result.final_message,
        registry_updates=react_result.accumulated_registry,
        structured_data=structured_data,
    )


# =============================================================================
# Admin MCP Server Task Tool
# =============================================================================


@tool
@track_tool_metrics(
    tool_name="mcp_server_task",
    agent_name=_AGENT_NAME,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: 5,
    window_seconds=lambda: 60,
    scope="user",
)
async def mcp_server_task_tool(
    server_name: Annotated[str, "The MCP server to interact with"],
    task: Annotated[str, "Natural language description of the task to accomplish"],
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Execute a multi-step task on an MCP server using a ReAct agent.

    Launches a ReAct agent with access to all tools from the specified MCP server.
    The agent follows the native MCP workflow: read documentation first, then
    execute tools based on the documentation.

    Use this for MCP servers requiring iterative interaction (e.g., Excalidraw:
    read format reference, then create diagram with correct elements).

    Examples:
        - server_name="excalidraw", task="Create a diagram of the water cycle"
        - server_name="google_flights", task="Find cheapest flight Paris to Tokyo next week"
    """
    server_tools = _get_mcp_server_tools_for_react(server_name)
    if not server_tools:
        logger.warning("mcp_react_no_tools", server_name=server_name)
        return UnifiedToolOutput.failure(
            message=f"No tools found for MCP server '{server_name}'",
            error_code="CONFIGURATION_ERROR",
        )

    return await _run_mcp_react_task(
        server_tools=server_tools,
        server_name=server_name,
        task=task,
        thread_prefix=f"mcp_react_{server_name}",
        runtime=runtime,
    )


# =============================================================================
# User MCP Server Task Tool
# =============================================================================


@tool
@track_tool_metrics(
    tool_name="mcp_user_server_task",
    agent_name=_AGENT_NAME,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: 5,
    window_seconds=lambda: 60,
    scope="user",
)
async def mcp_user_server_task_tool(
    server_id_prefix: Annotated[str, "First 8 characters of the user MCP server UUID"],
    server_name: Annotated[str, "Human-readable server name for display"],
    task: Annotated[str, "Natural language description of the task to accomplish"],
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Execute a multi-step task on a user MCP server using a ReAct agent.

    Launches a ReAct agent with access to all tools from the specified user MCP
    server. The agent follows the native MCP workflow: read documentation first,
    then execute tools based on the documentation.

    This is the per-user equivalent of mcp_server_task_tool for user-configured
    MCP servers with iterative_mode=true.
    """
    server_tools = _get_user_mcp_server_tools_for_react(server_id_prefix)
    if not server_tools:
        logger.warning(
            "mcp_user_react_no_tools",
            server_id_prefix=server_id_prefix,
            server_name=server_name,
        )
        return UnifiedToolOutput.failure(
            message=f"No tools found for user MCP server '{server_name}'",
            error_code="CONFIGURATION_ERROR",
        )

    return await _run_mcp_react_task(
        server_tools=server_tools,
        server_name=server_name,
        task=task,
        thread_prefix=f"mcp_user_react_{server_id_prefix}",
        runtime=runtime,
        extra_structured_data={"server_id_prefix": server_id_prefix},
    )
