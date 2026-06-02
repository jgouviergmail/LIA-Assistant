"""Tests for MCP argument sanitization.

Optional MCP parameters left unset are materialised as ``None`` by the Pydantic
args schema and, if forwarded verbatim, make strictly-typed MCP servers reject
the call ("parameter X is not of type string, is <nil>"). The adapters must drop
``None``-valued arguments before sending them to the server.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter
from src.infrastructure.mcp.utils import drop_none_values


class TestDropNoneValues:
    """The pure helper drops None but preserves valid falsy values."""

    def test_drops_only_none(self) -> None:
        result = drop_none_values(
            {"a": None, "b": False, "c": 0, "d": "", "e": [], "f": "x", "g": None}
        )
        assert result == {"b": False, "c": 0, "d": "", "e": [], "f": "x"}

    def test_empty(self) -> None:
        assert drop_none_values({}) == {}


class TestUserAdapterStripsNone:
    @pytest.mark.asyncio
    async def test_arun_omits_none_arguments(self) -> None:
        """UserMCPToolAdapter must not forward None-valued optional params."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="GITHUB REPOS",
            tool_name="search_repositories",
            description="Search repositories",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "sort": {"type": "string"},
                    "order": {"type": "string"},
                },
                "required": ["query"],
            },
        )

        mock_pool = MagicMock()
        mock_pool.call_tool = AsyncMock(return_value="ok")
        with patch(
            "src.infrastructure.mcp.user_pool.get_user_mcp_pool",
            return_value=mock_pool,
        ):
            await adapter._arun(query="lia", sort=None, order=None)

        sent = mock_pool.call_tool.call_args.kwargs["arguments"]
        assert sent == {"query": "lia"}


class TestAdminAdapterStripsNone:
    @pytest.mark.asyncio
    async def test_arun_omits_none_arguments(self) -> None:
        """MCPToolAdapter (admin) must not forward None-valued optional params."""
        adapter = MCPToolAdapter.from_mcp_tool(
            server_name="github",
            tool_name="search_repositories",
            description="Search repositories",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "sort": {"type": "string"},
                },
                "required": ["query"],
            },
        )

        mock_manager = MagicMock()
        mock_manager.call_tool = AsyncMock(return_value="ok")
        with patch(
            "src.infrastructure.mcp.client_manager.get_mcp_client_manager",
            return_value=mock_manager,
        ):
            await adapter._arun(query="lia", sort=None)

        # manager.call_tool(server_name, tool_name, arguments) — args[2] is the dict
        sent = mock_manager.call_tool.call_args.args[2]
        assert sent == {"query": "lia"}
