"""
Unit tests for MCP schemas.

Tests MCPServerConfig validation, MCPDiscoveredTool construction,
and MCPSettings JSON validation.

Phase: evolution F2 — MCP Support
Created: 2026-02-28
"""

import pytest

from src.infrastructure.mcp.schemas import (
    MCPDiscoveredTool,
    MCPServerConfig,
    MCPServerStatus,
    MCPTransportType,
)


class TestMCPTransportType:
    """Test MCPTransportType enum."""

    def test_stdio_value(self):
        assert MCPTransportType.STDIO == "stdio"

    def test_streamable_http_value(self):
        assert MCPTransportType.STREAMABLE_HTTP == "streamable_http"


class TestMCPServerConfig:
    """Test MCPServerConfig validation."""

    def test_stdio_valid(self):
        config = MCPServerConfig(
            transport=MCPTransportType.STDIO,
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        )
        assert config.command == "npx"
        assert len(config.args) == 3
        assert config.enabled is True
        assert config.hitl_required is None

    def test_stdio_without_command_raises(self):
        with pytest.raises(ValueError, match="command"):
            MCPServerConfig(
                transport=MCPTransportType.STDIO,
                command=None,
            )

    def test_streamable_http_valid(self):
        config = MCPServerConfig(
            transport=MCPTransportType.STREAMABLE_HTTP,
            url="https://mcp.example.com/api",
            headers={"Authorization": "Bearer token123"},
        )
        assert config.url == "https://mcp.example.com/api"
        assert config.headers is not None

    def test_streamable_http_without_url_raises(self):
        with pytest.raises(ValueError, match="url"):
            MCPServerConfig(
                transport=MCPTransportType.STREAMABLE_HTTP,
                url=None,
            )

    def test_repr_hides_sensitive_fields(self):
        """Verify repr=False hides headers and env from repr output."""
        config = MCPServerConfig(
            transport=MCPTransportType.STDIO,
            command="npx",
            env={"SECRET_KEY": "s3cr3t"},
        )
        config_repr = repr(config)
        assert "s3cr3t" not in config_repr

    def test_repr_hides_headers(self):
        config = MCPServerConfig(
            transport=MCPTransportType.STREAMABLE_HTTP,
            url="https://example.com",
            headers={"Authorization": "Bearer secret"},
        )
        config_repr = repr(config)
        assert "Bearer secret" not in config_repr

    def test_timeout_bounds(self):
        with pytest.raises(ValueError):
            MCPServerConfig(
                transport=MCPTransportType.STDIO,
                command="npx",
                timeout_seconds=3,  # Below minimum of 5
            )

    def test_disabled_server(self):
        config = MCPServerConfig(
            transport=MCPTransportType.STDIO,
            command="npx",
            enabled=False,
        )
        assert config.enabled is False

    def test_hitl_override(self):
        config = MCPServerConfig(
            transport=MCPTransportType.STDIO,
            command="npx",
            hitl_required=False,
        )
        assert config.hitl_required is False


class TestMCPDiscoveredTool:
    """Test MCPDiscoveredTool model."""

    def test_construction(self):
        tool = MCPDiscoveredTool(
            server_name="filesystem",
            tool_name="read_file",
            description="Read a file from disk",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                },
                "required": ["path"],
            },
        )
        assert tool.server_name == "filesystem"
        assert tool.tool_name == "read_file"
        assert "path" in tool.input_schema["properties"]

    def test_empty_schema(self):
        tool = MCPDiscoveredTool(
            server_name="test",
            tool_name="no_args",
            description="Tool with no arguments",
        )
        assert tool.input_schema == {}


class TestMCPServerStatus:
    """Test MCPServerStatus model."""

    def test_healthy(self):
        status = MCPServerStatus(
            server_name="fs",
            connected=True,
            tool_count=5,
            last_health_check="2026-02-28T12:00:00Z",
        )
        assert status.connected is True
        assert status.tool_count == 5
        assert status.error is None

    def test_unhealthy(self):
        status = MCPServerStatus(
            server_name="fs",
            connected=False,
            error="Connection refused",
        )
        assert status.connected is False
        assert status.error == "Connection refused"


class TestMCPSettingsJsonValidator:
    """Test MCPSettings JSON validation."""

    def test_valid_json(self):
        from src.core.config.mcp import MCPSettings

        s = MCPSettings(mcp_servers_config='{"test": {"transport": "stdio"}}')
        assert s.mcp_servers_config == '{"test": {"transport": "stdio"}}'

    def test_empty_json(self):
        from src.core.config.mcp import MCPSettings

        s = MCPSettings(mcp_servers_config="{}")
        assert s.mcp_servers_config == "{}"

    def test_invalid_json_raises(self):
        from src.core.config.mcp import MCPSettings

        with pytest.raises(ValueError, match="invalid JSON"):
            MCPSettings(mcp_servers_config="{invalid json")
