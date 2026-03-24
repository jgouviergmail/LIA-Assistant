"""
Unit tests for MCP ReAct tools.

Tests _MCPReActWrapper registry accumulation and mcp_server_task_tool.

Phase: ADR-062 — Agent Initiative Phase + MCP Iterative Support
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.agents.tools.mcp_react_tools import (
    _get_mcp_server_tools_for_react,
    _MCPReActWrapper,
)


@pytest.mark.unit
class TestMCPReActWrapper:
    """Tests for _MCPReActWrapper."""

    def _make_adapter(
        self,
        tool_name: str = "create_view",
        description: str = "Create a view",
    ) -> MagicMock:
        adapter = MagicMock()
        adapter.mcp_tool_name = tool_name
        adapter.description = description
        adapter.args_schema = None
        return adapter

    def test_wrapper_exposes_short_name(self) -> None:
        adapter = self._make_adapter(tool_name="create_view")
        wrapper = _MCPReActWrapper(adapter)
        assert wrapper.name == "create_view"

    def test_wrapper_exposes_description(self) -> None:
        adapter = self._make_adapter(description="Create an Excalidraw view")
        wrapper = _MCPReActWrapper(adapter)
        assert "Excalidraw" in wrapper.description

    async def test_wrapper_returns_string(self) -> None:
        adapter = self._make_adapter()
        result_obj = MagicMock()
        result_obj.message = "View created successfully"
        result_obj.registry_updates = {}
        adapter._arun = AsyncMock(return_value=result_obj)

        wrapper = _MCPReActWrapper(adapter)
        result = await wrapper._arun(elements="[]")
        assert isinstance(result, str)
        assert result == "View created successfully"

    async def test_wrapper_accumulates_registry(self) -> None:
        adapter = self._make_adapter()
        result_obj = MagicMock()
        result_obj.message = "View created"
        result_obj.registry_updates = {"mcp_app_123": {"type": "MCP_APP", "html": "<div>"}}
        adapter._arun = AsyncMock(return_value=result_obj)

        wrapper = _MCPReActWrapper(adapter)
        await wrapper._arun(elements="[]")

        assert "mcp_app_123" in wrapper._accumulated_registry
        assert wrapper._accumulated_registry["mcp_app_123"]["type"] == "MCP_APP"

    async def test_wrapper_accumulates_across_calls(self) -> None:
        adapter = self._make_adapter()

        # First call: read_me (no registry)
        result1 = MagicMock()
        result1.message = "Documentation content"
        result1.registry_updates = {}

        # Second call: create_view (with MCP App registry)
        result2 = MagicMock()
        result2.message = "View created"
        result2.registry_updates = {"app_1": {"type": "MCP_APP"}}

        adapter._arun = AsyncMock(side_effect=[result1, result2])

        wrapper = _MCPReActWrapper(adapter)
        await wrapper._arun()  # read_me
        await wrapper._arun(elements="[]")  # create_view

        assert len(wrapper._accumulated_registry) == 1
        assert "app_1" in wrapper._accumulated_registry

    async def test_wrapper_handles_no_registry_attr(self) -> None:
        adapter = self._make_adapter()
        result_obj = MagicMock(spec=["message"])
        result_obj.message = "result"
        adapter._arun = AsyncMock(return_value=result_obj)

        wrapper = _MCPReActWrapper(adapter)
        result = await wrapper._arun()
        assert result == "result"
        assert wrapper._accumulated_registry == {}


@pytest.mark.unit
class TestGetMCPServerToolsForReact:
    """Tests for _get_mcp_server_tools_for_react."""

    def test_returns_empty_for_unknown_server(self) -> None:
        from unittest.mock import patch

        with patch(
            "src.domains.agents.tools.mcp_react_tools.get_all_tools",
            return_value={},
        ):
            result = _get_mcp_server_tools_for_react("nonexistent")
            assert result == []
