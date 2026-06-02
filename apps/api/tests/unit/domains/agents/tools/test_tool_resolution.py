"""Tests for the shared tool-instance resolver used by ReAct and the pipeline.

The resolver mirrors the pipeline executor's two-step lookup so ReAct mode can
use user MCP tools, whose instances live only in the per-request
``user_mcp_tools_ctx`` ContextVar (not the global tool registry).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.core.constants import MCP_USER_TOOL_NAME_PREFIX
from src.core.context import UserMCPToolsContext, user_mcp_tools_ctx
from src.domains.agents.tools.tool_resolution import (
    resolve_tool_instance,
    resolve_tool_instance_named,
    resolve_tool_manifest,
    resolve_tool_manifest_named,
)


def _register_dummy_global_tool(name: str) -> object:
    """Register a throwaway tool in the global registry (idempotent, unique name)."""
    from langchain_core.tools import StructuredTool

    from src.domains.agents.tools.tool_registry import get_tool as _get
    from src.domains.agents.tools.tool_registry import register_external_tool

    existing = _get(name)
    if existing is not None:
        return existing

    async def _fn() -> str:
        return "ok"

    tool = StructuredTool.from_function(coroutine=_fn, name=name, description="dummy")
    register_external_tool(tool)
    return tool


class TestResolveToolInstance:
    """Resolution order: global registry first, then user MCP ContextVar."""

    def test_user_mcp_tool_resolved_from_contextvar(self) -> None:
        """A user MCP tool present only in the ContextVar must be resolvable.

        This is the ReAct bug: get_tool() (global registry) returns None for
        user MCP tools, so they were dropped. The resolver must fall back to
        user_mcp_tools_ctx.tool_instances.
        """
        tool_name = f"{MCP_USER_TOOL_NAME_PREFIX}_770baa3e_get_indicator"
        instance = MagicMock(name="user_mcp_adapter")

        ctx = UserMCPToolsContext()
        ctx.tool_instances[tool_name] = instance
        manifest = MagicMock()
        manifest.name = tool_name
        ctx.tool_manifests = [manifest]

        token = user_mcp_tools_ctx.set(ctx)
        try:
            assert resolve_tool_instance(tool_name) is instance
        finally:
            user_mcp_tools_ctx.reset(token)

    def test_returns_none_when_absent_everywhere(self) -> None:
        """Unknown tool name resolves to None (no ContextVar, not in registry)."""
        assert resolve_tool_instance("definitely_not_a_real_tool_xyz") is None

    def test_hallucinated_suffix_resolved_via_contextvar(self) -> None:
        """LLM-hallucinated suffix is stripped and resolved (pipeline parity)."""
        real_name = f"{MCP_USER_TOOL_NAME_PREFIX}_770baa3e_get_indicator"
        instance = MagicMock(name="user_mcp_adapter")

        ctx = UserMCPToolsContext()
        ctx.tool_instances[real_name] = instance
        manifest = MagicMock()
        manifest.name = real_name
        ctx.tool_manifests = [manifest]

        token = user_mcp_tools_ctx.set(ctx)
        try:
            # Some models append a "_tool" suffix that doesn't exist on the server
            assert resolve_tool_instance(f"{real_name}_tool") is instance
        finally:
            user_mcp_tools_ctx.reset(token)


class TestResolveToolInstanceNamed:
    """The named resolver returns (tool, canonical_name) for pipeline parity.

    Encodes the full contract the pipeline executor relies on:
    global exact → global with hallucinated suffix stripped (admin MCP) →
    user MCP ContextVar (exact then fuzzy) → not found.
    """

    @pytest.fixture(autouse=True)
    def _restore_global_registry(self):
        """Remove any throwaway tools registered during a test (no leak).

        The dummy-tool helper writes into the process-global tool registry; this
        snapshots the names before and pops anything added afterwards so the
        global state is identical to before the test.
        """
        from src.domains.agents.tools import tool_registry

        before = set(tool_registry.list_tool_names())
        yield
        for name in set(tool_registry.list_tool_names()) - before:
            tool_registry._TOOL_REGISTRY.pop(name, None)

    def test_global_exact_returns_same_name(self) -> None:
        tool = _register_dummy_global_tool("char_glob_exact_xyz")
        assert resolve_tool_instance_named("char_glob_exact_xyz") == (tool, "char_glob_exact_xyz")

    def test_global_hallucinated_suffix_stripped_returns_canonical(self) -> None:
        """An admin/native tool reached via a hallucinated '_tool' suffix is stripped."""
        tool = _register_dummy_global_tool("char_glob_indicator")
        resolved_tool, canonical = resolve_tool_instance_named("char_glob_indicator_tool")
        assert resolved_tool is tool
        assert canonical == "char_glob_indicator"

    def test_user_mcp_fuzzy_returns_canonical(self) -> None:
        real_name = f"{MCP_USER_TOOL_NAME_PREFIX}_770baa3e_get_indicator"
        instance = MagicMock(name="user_mcp_adapter")
        ctx = UserMCPToolsContext()
        ctx.tool_instances[real_name] = instance
        manifest = MagicMock()
        manifest.name = real_name
        ctx.tool_manifests = [manifest]

        token = user_mcp_tools_ctx.set(ctx)
        try:
            resolved_tool, canonical = resolve_tool_instance_named(f"{real_name}_tool")
        finally:
            user_mcp_tools_ctx.reset(token)

        assert resolved_tool is instance
        assert canonical == real_name

    def test_not_found_returns_none_and_original_name(self) -> None:
        assert resolve_tool_instance_named("definitely_not_a_real_tool_xyz") == (
            None,
            "definitely_not_a_real_tool_xyz",
        )


class TestResolveToolManifest:
    """Manifest resolution: global agent registry first, then user MCP ContextVar."""

    def test_user_mcp_manifest_resolved_from_contextvar(self) -> None:
        """A user MCP manifest present only in the ContextVar must be resolvable.

        The agent_registry does not know user MCP tools, so display-metadata and
        other manifest consumers must fall back to user_mcp_tools_ctx instead of
        emitting ToolManifestNotFound.
        """
        name = f"{MCP_USER_TOOL_NAME_PREFIX}_770baa3e_get_indicator"
        manifest = SimpleNamespace(name=name, display=SimpleNamespace(emoji="x"))

        ctx = UserMCPToolsContext()
        ctx.tool_manifests = [manifest]

        token = user_mcp_tools_ctx.set(ctx)
        try:
            assert resolve_tool_manifest(name) is manifest
        finally:
            user_mcp_tools_ctx.reset(token)

    def test_returns_none_when_absent_everywhere(self) -> None:
        """Unknown manifest name resolves to None (not registered, no ContextVar)."""
        assert resolve_tool_manifest("definitely_not_a_real_tool_xyz") is None


class TestResolveToolManifestNamed:
    """The named manifest resolver returns (manifest, canonical_name)."""

    def test_user_mcp_fuzzy_returns_canonical(self) -> None:
        name = f"{MCP_USER_TOOL_NAME_PREFIX}_770baa3e_get_indicator"
        manifest = SimpleNamespace(name=name, display=SimpleNamespace(emoji="x"))
        ctx = UserMCPToolsContext()
        ctx.tool_manifests = [manifest]

        token = user_mcp_tools_ctx.set(ctx)
        try:
            resolved, canonical = resolve_tool_manifest_named(f"{name}_tool")
        finally:
            user_mcp_tools_ctx.reset(token)

        assert resolved is manifest
        assert canonical == name

    def test_not_found_returns_none_and_original_name(self) -> None:
        assert resolve_tool_manifest_named("definitely_not_a_real_tool_xyz") == (
            None,
            "definitely_not_a_real_tool_xyz",
        )


class TestDisplayMetadataUsesResolver:
    """get_tool_display_metadata must resolve user MCP manifests via the ContextVar."""

    def test_display_metadata_from_user_mcp_ctx(self) -> None:
        """Display metadata of a ctx-only user MCP tool is returned (no warning path)."""
        from src.domains.agents.utils.execution_metadata import get_tool_display_metadata

        name = f"{MCP_USER_TOOL_NAME_PREFIX}_770baa3e_get_indicator"
        display = SimpleNamespace(emoji="🔌", i18n_key="mcp_tool", visible=True, category="tool")
        manifest = SimpleNamespace(name=name, display=display)

        ctx = UserMCPToolsContext()
        ctx.tool_manifests = [manifest]

        token = user_mcp_tools_ctx.set(ctx)
        try:
            assert get_tool_display_metadata(name) is display
        finally:
            user_mcp_tools_ctx.reset(token)
