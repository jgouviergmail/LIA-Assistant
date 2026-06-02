"""Tests for ReactToolSelector — user MCP tool inclusion and HITL parity.

Regression guard for the ReAct/pipeline asymmetry: user MCP tools live only in
``user_mcp_tools_ctx`` (not the global registry), so the selector must resolve
them via the shared resolver and must read their HITL flag from the in-hand
manifest (the agent_registry does not know user MCP tools).
"""

from types import SimpleNamespace
from uuid import UUID

from src.core.config import settings
from src.core.constants import MCP_ITERATIVE_TASK_SUFFIX, MCP_USER_TOOL_NAME_PREFIX
from src.core.context import (
    UserMCPToolsContext,
    request_tool_manifests_ctx,
    user_mcp_tools_ctx,
)
from src.domains.agents.services.react_tool_selector import ReactToolSelector
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter

_SERVER_ID = UUID("770baa3e-1111-2222-3333-444455556666")
_SERVER_PREFIX = str(_SERVER_ID)[:8]
_TASK_TOOL_NAME = f"{MCP_USER_TOOL_NAME_PREFIX}_{_SERVER_PREFIX}{MCP_ITERATIVE_TASK_SUFFIX}"


def _make_user_adapter(
    tool_name: str, *, app_resource_uri: str | None = None
) -> UserMCPToolAdapter:
    return UserMCPToolAdapter.from_discovered_tool(
        server_id=_SERVER_ID,
        user_id=UUID(int=1),
        server_name="atars",
        tool_name=tool_name,
        description=f"User MCP tool {tool_name}",
        input_schema={"type": "object", "properties": {}},
        app_resource_uri=app_resource_uri,
    )


def _manifest(name: str, *, hitl: bool) -> SimpleNamespace:
    return SimpleNamespace(name=name, permissions=SimpleNamespace(hitl_required=hitl))


class TestReactToolSelectorUserMCP:
    """User MCP tools must be selectable in ReAct mode (pipeline parity)."""

    def test_user_mcp_tool_is_selected_not_skipped(self) -> None:
        """A user MCP tool present only in the ContextVar must be wrapped, not dropped."""
        adapter = _make_user_adapter("get_indicator")
        manifest = _manifest(adapter.name, hitl=False)

        ctx = UserMCPToolsContext()
        ctx.tool_instances[adapter.name] = adapter
        ctx.tool_manifests = [manifest]

        man_token = request_tool_manifests_ctx.set([manifest])
        ctx_token = user_mcp_tools_ctx.set(ctx)
        try:
            wrapped, hitl_map = ReactToolSelector().select(intelligence=None)
        finally:
            user_mcp_tools_ctx.reset(ctx_token)
            request_tool_manifests_ctx.reset(man_token)

        assert adapter.name in {t.name for t in wrapped}
        assert adapter.name in hitl_map

    def test_user_mcp_hitl_read_from_manifest(self) -> None:
        """HITL flag must come from the manifest (agent_registry has no user MCP)."""
        adapter = _make_user_adapter("delete_data")
        manifest = _manifest(adapter.name, hitl=True)

        ctx = UserMCPToolsContext()
        ctx.tool_instances[adapter.name] = adapter
        ctx.tool_manifests = [manifest]

        man_token = request_tool_manifests_ctx.set([manifest])
        ctx_token = user_mcp_tools_ctx.set(ctx)
        try:
            wrapped, hitl_map = ReactToolSelector().select(intelligence=None)
        finally:
            user_mcp_tools_ctx.reset(ctx_token)
            request_tool_manifests_ctx.reset(man_token)

        assert hitl_map.get(adapter.name) is True
        wrapper = next(t for t in wrapped if t.name == adapter.name)
        assert wrapper.hitl_required is True


class TestReactIterativeExpansion:
    """In ReAct, iterative user MCP servers expose individual tools (option B).

    Exception: MCP App servers (tools with app_resource_uri) keep the opaque
    task tool, because they need the dedicated MCP-app prompt + model.
    """

    def test_iterative_data_server_expanded_to_individual_tools(self) -> None:
        """A non-App iterative server: task tool is replaced by its individual tools."""
        ind1 = _make_user_adapter("get_indicator")
        ind2 = _make_user_adapter("get_signal_summary")
        task_manifest = _manifest(_TASK_TOOL_NAME, hitl=False)

        ctx = UserMCPToolsContext()
        ctx.tool_instances[_TASK_TOOL_NAME] = SimpleNamespace(name=_TASK_TOOL_NAME)
        ctx.tool_instances[ind1.name] = ind1
        ctx.tool_instances[ind2.name] = ind2
        ctx.tool_manifests = [task_manifest]

        man_token = request_tool_manifests_ctx.set([task_manifest])
        ctx_token = user_mcp_tools_ctx.set(ctx)
        try:
            wrapped, hitl_map = ReactToolSelector().select(intelligence=None)
        finally:
            user_mcp_tools_ctx.reset(ctx_token)
            request_tool_manifests_ctx.reset(man_token)

        names = {t.name for t in wrapped}
        assert ind1.name in names
        assert ind2.name in names
        assert _TASK_TOOL_NAME not in names  # opaque task tool replaced

    def test_iterative_app_server_keeps_task_tool(self) -> None:
        """An MCP App iterative server keeps the task tool, individual tools hidden."""
        from src.domains.agents.tools.mcp_react_tools import mcp_user_server_task_tool

        app_tool = _make_user_adapter("create_view", app_resource_uri="ui://widget")
        task_instance = mcp_user_server_task_tool.model_copy(update={"name": _TASK_TOOL_NAME})
        task_manifest = _manifest(_TASK_TOOL_NAME, hitl=False)

        ctx = UserMCPToolsContext()
        ctx.tool_instances[_TASK_TOOL_NAME] = task_instance
        ctx.tool_instances[app_tool.name] = app_tool
        ctx.tool_manifests = [task_manifest]

        man_token = request_tool_manifests_ctx.set([task_manifest])
        ctx_token = user_mcp_tools_ctx.set(ctx)
        try:
            wrapped, hitl_map = ReactToolSelector().select(intelligence=None)
        finally:
            user_mcp_tools_ctx.reset(ctx_token)
            request_tool_manifests_ctx.reset(man_token)

        names = {t.name for t in wrapped}
        assert _TASK_TOOL_NAME in names  # app server keeps the task tool
        assert app_tool.name not in names  # individual app tools stay hidden

    def test_expansion_disabled_keeps_task_tool(self, monkeypatch) -> None:
        """With the feature flag off, the iterative task tool is kept (no expansion)."""
        from src.domains.agents.tools.mcp_react_tools import mcp_user_server_task_tool

        monkeypatch.setattr(settings, "react_mcp_expand_iterative_enabled", False)

        ind1 = _make_user_adapter("get_indicator")
        task_instance = mcp_user_server_task_tool.model_copy(update={"name": _TASK_TOOL_NAME})
        task_manifest = _manifest(_TASK_TOOL_NAME, hitl=False)

        ctx = UserMCPToolsContext()
        ctx.tool_instances[_TASK_TOOL_NAME] = task_instance
        ctx.tool_instances[ind1.name] = ind1
        ctx.tool_manifests = [task_manifest]

        man_token = request_tool_manifests_ctx.set([task_manifest])
        ctx_token = user_mcp_tools_ctx.set(ctx)
        try:
            wrapped, _hitl_map = ReactToolSelector().select(intelligence=None)
        finally:
            user_mcp_tools_ctx.reset(ctx_token)
            request_tool_manifests_ctx.reset(man_token)

        names = {t.name for t in wrapped}
        assert _TASK_TOOL_NAME in names  # flag off → task tool kept
        assert ind1.name not in names  # individual tools NOT exposed
