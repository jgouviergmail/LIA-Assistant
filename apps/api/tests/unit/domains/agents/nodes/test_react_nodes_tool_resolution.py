"""Tests for ReAct node tool rebuilding — user MCP resolution parity.

``_rebuild_wrapped_tools`` is called by react_call_model (binding) and
react_execute_tools (execution). It must resolve user MCP tool names from the
ContextVar, otherwise bound/selected user MCP tools would silently vanish at
execution time.
"""

from uuid import UUID

from src.core.context import UserMCPToolsContext, user_mcp_tools_ctx
from src.domains.agents.nodes.react_nodes import _rebuild_wrapped_tools
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter


def _make_user_adapter(tool_name: str) -> UserMCPToolAdapter:
    return UserMCPToolAdapter.from_discovered_tool(
        server_id=UUID("770baa3e-1111-2222-3333-444455556666"),
        user_id=UUID(int=1),
        server_name="atars",
        tool_name=tool_name,
        description=f"User MCP tool {tool_name}",
        input_schema={"type": "object", "properties": {}},
    )


def test_rebuild_resolves_user_mcp_tool_from_contextvar() -> None:
    """A user MCP tool name must rebuild into a wrapper via the ContextVar."""
    adapter = _make_user_adapter("get_indicator")

    ctx = UserMCPToolsContext()
    ctx.tool_instances[adapter.name] = adapter

    token = user_mcp_tools_ctx.set(ctx)
    try:
        wrappers = _rebuild_wrapped_tools([adapter.name], {adapter.name: True})
    finally:
        user_mcp_tools_ctx.reset(token)

    assert len(wrappers) == 1
    assert wrappers[0].name == adapter.name
    assert wrappers[0].hitl_required is True
