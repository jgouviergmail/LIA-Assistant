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
    """Wrapper that converts MCPToolAdapter output to string for ReAct LLM.

    The ReAct agent needs string results to reason about tool outputs.
    MCPToolAdapter returns UnifiedToolOutput (rich object with registry items).

    This wrapper:
    - Returns ``result.message`` (string) to the ReAct LLM
    - Accumulates all ``registry_updates`` (e.g., MCP App HTML widgets) in a
      PrivateAttr for later propagation to the parent graph
    - Exposes the original tool's ``args_schema`` for correct tool calling
    - Uses the short MCP tool name (``create_view``, not ``mcp_excalidraw_create_view``)
    """

    _inner: MCPToolAdapter = PrivateAttr()
    _accumulated_registry: dict[str, Any] = PrivateAttr(default_factory=dict)

    def __init__(self, inner: MCPToolAdapter) -> None:
        """Initialize wrapper from an MCPToolAdapter.

        Args:
            inner: The original MCPToolAdapter to wrap.
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

        Args:
            **kwargs: Tool arguments.

        Returns:
            String representation of the tool result for ReAct LLM context.
        """
        result = await self._inner._arun(**kwargs)

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


# =============================================================================
# MCP Server Task Tool — Primary entry point
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
        logger.warning(
            "mcp_react_no_tools",
            server_name=server_name,
        )
        return UnifiedToolOutput.failure(
            message=f"No tools found for MCP server '{server_name}'",
            error_code="CONFIGURATION_ERROR",
        )

    runner = ReactSubAgentRunner("mcp_react_agent", "mcp_react_agent_prompt")
    react_result = await runner.run(
        task=task,
        tools=server_tools,
        prompt_vars={"server_name": server_name},
        parent_runtime=runtime,
        thread_prefix=f"mcp_react_{server_name}",
        recursion_limit=settings.mcp_react_max_iterations,
        display_name=f"MCP Iterative: {server_name}",
    )

    # Token tracking: callbacks are propagated to the ReAct internal graph
    # via nested_config. TokenTrackingCallback tracks tokens automatically.
    # Tokens appear in debug panel under the ReAct internal node name.

    # Propagate MCP App registry items (Excalidraw widgets, etc.)
    return UnifiedToolOutput.data_success(
        message=react_result.final_message,
        registry_updates=react_result.accumulated_registry,
        structured_data={
            "server_name": server_name,
            "task": task,
            "iterations": react_result.iteration_count,
            "duration_ms": react_result.duration_ms,
        },
    )
