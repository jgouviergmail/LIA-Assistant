"""
Unit tests for MCPClientManager.

Tests connection lifecycle, tool discovery, rate limiting,
error handling, and shutdown behavior.

Phase: evolution F2 — MCP Support
Created: 2026-02-28
"""

import asyncio
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.mcp.client_manager import MCPClientManager, _parse_server_configs
from src.infrastructure.mcp.schemas import MCPServerConfig, MCPTransportType


class TestMCPClientManagerCallTool:
    """Test tool invocation with rate limiting."""

    @pytest.fixture
    def manager(self):
        mgr = MCPClientManager()
        # Set up a mock session
        mock_session = AsyncMock()
        mgr._sessions["test_server"] = mock_session
        mgr._servers["test_server"] = MCPServerConfig(
            transport=MCPTransportType.STDIO,
            command="npx",
            timeout_seconds=30,
        )
        mgr._call_timestamps["test_server"] = deque()
        return mgr

    @pytest.mark.asyncio
    async def test_successful_call(self, manager):
        """Test successful tool call returns content."""
        mock_result = MagicMock()
        mock_result.isError = False
        mock_content = MagicMock()
        mock_content.text = "Hello World"
        mock_result.content = [mock_content]

        manager._sessions["test_server"].call_tool = AsyncMock(return_value=mock_result)

        result = await manager.call_tool("test_server", "greet", {"name": "Alice"})
        assert result == "Hello World"

    @pytest.mark.asyncio
    async def test_call_error_flag(self, manager):
        """Test CallToolResult.isError=True raises RuntimeError."""
        mock_result = MagicMock()
        mock_result.isError = True
        mock_content = MagicMock()
        mock_content.text = "Tool execution failed"
        mock_result.content = [mock_content]

        manager._sessions["test_server"].call_tool = AsyncMock(return_value=mock_result)

        with pytest.raises(RuntimeError, match="returned error"):
            await manager.call_tool("test_server", "failing_tool", {})

    @pytest.mark.asyncio
    async def test_server_not_connected(self, manager):
        """Test call to non-existent server raises error."""
        with pytest.raises(RuntimeError, match="not connected"):
            await manager.call_tool("nonexistent", "tool", {})

    @pytest.mark.asyncio
    async def test_timeout_handling(self, manager):
        """Test timeout propagation raises TimeoutError."""

        async def mock_wait_for(coro, timeout):
            # Close the coroutine to avoid warning
            coro.close()
            raise TimeoutError()

        with (
            patch("src.infrastructure.mcp.client_manager.settings") as mock_settings,
            patch("src.infrastructure.mcp.client_manager.asyncio.wait_for", mock_wait_for),
        ):
            mock_settings.mcp_rate_limit_calls = 100
            mock_settings.mcp_rate_limit_window = 60
            mock_settings.mcp_tool_timeout_seconds = 30

            with pytest.raises(asyncio.TimeoutError):
                await manager.call_tool("test_server", "tool", {})

    @pytest.mark.asyncio
    async def test_rate_limiting_enforcement(self, manager):
        """Test rate limit blocks excess calls."""
        mock_result = MagicMock()
        mock_result.isError = False
        mock_content = MagicMock()
        mock_content.text = "ok"
        mock_result.content = [mock_content]
        manager._sessions["test_server"].call_tool = AsyncMock(return_value=mock_result)

        with patch("src.infrastructure.mcp.client_manager.settings") as mock_settings:
            mock_settings.mcp_rate_limit_calls = 2  # Very low limit
            mock_settings.mcp_rate_limit_window = 60
            mock_settings.mcp_tool_timeout_seconds = 30

            # First 2 calls should succeed
            await manager.call_tool("test_server", "tool", {})
            await manager.call_tool("test_server", "tool", {})

            # Third call should be rate-limited
            with pytest.raises(RuntimeError, match="Rate limit exceeded"):
                await manager.call_tool("test_server", "tool", {})


class TestMCPClientManagerShutdown:
    """Test graceful shutdown."""

    @pytest.mark.asyncio
    async def test_shutdown_closes_exit_stacks(self):
        manager = MCPClientManager()
        mock_exit_stack = AsyncMock()
        manager._exit_stacks["server1"] = mock_exit_stack
        manager._sessions["server1"] = AsyncMock()
        manager._servers["server1"] = MCPServerConfig(
            transport=MCPTransportType.STDIO, command="npx"
        )
        manager._call_timestamps["server1"] = deque()

        await manager.shutdown()

        mock_exit_stack.__aexit__.assert_called_once()
        assert len(manager._sessions) == 0
        assert len(manager._servers) == 0

    @pytest.mark.asyncio
    async def test_shutdown_handles_errors(self):
        """Shutdown should not raise even if exit stack fails."""
        manager = MCPClientManager()
        mock_exit_stack = AsyncMock()
        mock_exit_stack.__aexit__ = AsyncMock(side_effect=RuntimeError("cleanup error"))
        manager._exit_stacks["server1"] = mock_exit_stack
        manager._sessions["server1"] = AsyncMock()

        # Should not raise
        await manager.shutdown()
        assert len(manager._sessions) == 0


class TestParseServerConfigs:
    """Test configuration parsing."""

    def test_empty_config(self):
        with patch("src.infrastructure.mcp.client_manager.settings") as mock_settings:
            mock_settings.mcp_servers_config_path = None
            mock_settings.mcp_servers_config = "{}"
            configs = _parse_server_configs()
        assert configs == {}

    def test_inline_json(self):
        with patch("src.infrastructure.mcp.client_manager.settings") as mock_settings:
            mock_settings.mcp_servers_config_path = None
            mock_settings.mcp_servers_config = (
                '{"fs": {"transport": "stdio", "command": "npx", ' '"args": ["-y", "server"]}}'
            )
            configs = _parse_server_configs()
        assert "fs" in configs
        assert configs["fs"].command == "npx"

    def test_invalid_inline_json(self):
        with patch("src.infrastructure.mcp.client_manager.settings") as mock_settings:
            mock_settings.mcp_servers_config_path = None
            mock_settings.mcp_servers_config = "{invalid"
            configs = _parse_server_configs()
        assert configs == {}

    def test_file_config(self, tmp_path):
        config_file = tmp_path / "mcp.json"
        config_file.write_text(
            '{"db": {"transport": "stdio", "command": "python", "args": ["server.py"]}}'
        )

        with patch("src.infrastructure.mcp.client_manager.settings") as mock_settings:
            mock_settings.mcp_servers_config_path = str(config_file)
            configs = _parse_server_configs()
        assert "db" in configs
        assert configs["db"].command == "python"

    def test_file_not_found(self):
        with patch("src.infrastructure.mcp.client_manager.settings") as mock_settings:
            mock_settings.mcp_servers_config_path = "/nonexistent/path.json"
            configs = _parse_server_configs()
        assert configs == {}


class TestMCPClientManagerHealthCheck:
    """Test health check functionality."""

    @pytest.mark.asyncio
    async def test_healthy_server(self):
        manager = MCPClientManager()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.tools = [MagicMock(), MagicMock()]
        mock_session.list_tools = AsyncMock(return_value=mock_result)
        manager._sessions["server1"] = mock_session

        with patch("src.infrastructure.mcp.client_manager.settings") as mock_settings:
            mock_settings.mcp_tool_timeout_seconds = 30
            status = await manager.health_check("server1")

        assert status.connected is True
        assert status.tool_count == 2

    @pytest.mark.asyncio
    async def test_unhealthy_server(self):
        manager = MCPClientManager()
        status = await manager.health_check("nonexistent")
        assert status.connected is False
        assert "Not connected" in status.error
