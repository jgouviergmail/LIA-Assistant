"""
Unit tests for MCP security module.

Tests SSRF prevention, server config validation, and HITL resolution.

Phase: evolution F2 — MCP Support
Created: 2026-02-28
"""

from unittest.mock import AsyncMock, patch

from src.infrastructure.mcp.schemas import MCPServerConfig, MCPTransportType
from src.infrastructure.mcp.security import (
    resolve_hitl_requirement,
    validate_http_endpoint,
    validate_server_config,
)


def _mock_async_getaddrinfo(return_value):
    """Create a mock for loop.getaddrinfo that returns an awaitable."""
    mock_loop = AsyncMock()
    mock_loop.getaddrinfo = AsyncMock(return_value=return_value)
    return mock_loop


class TestValidateServerConfig:
    """Test server configuration validation."""

    async def test_stdio_valid(self):
        config = MCPServerConfig(
            transport=MCPTransportType.STDIO,
            command="npx",
            args=["-y", "server"],
        )
        errors = await validate_server_config(config)
        assert errors == []

    async def test_stdio_without_command(self):
        # MCPServerConfig validation catches this first, but let's test
        # the security layer directly with a mock
        config = MCPServerConfig.__new__(MCPServerConfig)
        object.__setattr__(config, "transport", MCPTransportType.STDIO)
        object.__setattr__(config, "command", None)
        object.__setattr__(config, "args", [])
        object.__setattr__(config, "url", None)
        object.__setattr__(config, "headers", None)
        object.__setattr__(config, "env", None)
        object.__setattr__(config, "timeout_seconds", 30)
        object.__setattr__(config, "enabled", True)
        object.__setattr__(config, "hitl_required", None)
        errors = await validate_server_config(config)
        assert any("command" in e.lower() for e in errors)

    async def test_stdio_path_traversal(self):
        config = MCPServerConfig(
            transport=MCPTransportType.STDIO,
            command="/usr/bin/python",
        )
        errors = await validate_server_config(config)
        assert any("path" in e.lower() for e in errors)

    async def test_http_valid(self):
        config = MCPServerConfig(
            transport=MCPTransportType.STREAMABLE_HTTP,
            url="https://mcp.example.com/api",
        )
        mock_loop = _mock_async_getaddrinfo(
            [
                (2, 1, 6, "", ("93.184.216.34", 443)),
            ]
        )
        with patch(
            "src.infrastructure.mcp.security.asyncio.get_running_loop", return_value=mock_loop
        ):
            errors = await validate_server_config(config)
        assert errors == []


class TestValidateHttpEndpoint:
    """Test SSRF prevention for HTTP endpoints."""

    async def test_https_public_url(self):
        mock_loop = _mock_async_getaddrinfo(
            [
                (2, 1, 6, "", ("93.184.216.34", 443)),
            ]
        )
        with patch(
            "src.infrastructure.mcp.security.asyncio.get_running_loop", return_value=mock_loop
        ):
            is_valid, error = await validate_http_endpoint("https://mcp.example.com/api")
        assert is_valid is True
        assert error is None

    async def test_http_blocked(self):
        """HTTP (non-HTTPS) must be blocked."""
        is_valid, error = await validate_http_endpoint("http://mcp.example.com/api")
        assert is_valid is False
        assert "HTTPS" in error

    async def test_localhost_blocked(self):
        is_valid, error = await validate_http_endpoint("https://localhost:8080/mcp")
        assert is_valid is False
        assert "Blocked hostname" in error

    async def test_private_ip_blocked(self):
        mock_loop = _mock_async_getaddrinfo(
            [
                (2, 1, 6, "", ("192.168.1.100", 443)),
            ]
        )
        with patch(
            "src.infrastructure.mcp.security.asyncio.get_running_loop", return_value=mock_loop
        ):
            is_valid, error = await validate_http_endpoint("https://internal.corp.com/mcp")
        assert is_valid is False
        assert "Blocked IP" in error

    async def test_ipv4_mapped_ipv6_blocked(self):
        """::ffff:127.0.0.1 should be normalized and blocked."""
        mock_loop = _mock_async_getaddrinfo(
            [
                (10, 1, 6, "", ("::ffff:127.0.0.1", 443, 0, 0)),
            ]
        )
        with patch(
            "src.infrastructure.mcp.security.asyncio.get_running_loop", return_value=mock_loop
        ):
            is_valid, error = await validate_http_endpoint("https://sneaky.example.com/mcp")
        assert is_valid is False

    async def test_metadata_endpoint_blocked(self):
        is_valid, error = await validate_http_endpoint("https://169.254.169.254/metadata")
        assert is_valid is False

    async def test_internal_suffix_blocked(self):
        is_valid, error = await validate_http_endpoint("https://service.internal/mcp")
        assert is_valid is False
        assert "suffix" in error.lower()

    async def test_dns_failure(self):
        import socket

        mock_loop = AsyncMock()
        mock_loop.getaddrinfo = AsyncMock(side_effect=socket.gaierror("Name resolution failed"))
        with patch(
            "src.infrastructure.mcp.security.asyncio.get_running_loop", return_value=mock_loop
        ):
            is_valid, error = await validate_http_endpoint("https://nonexistent.example.com/mcp")
        assert is_valid is False
        assert "DNS" in error


class TestResolveHitlRequirement:
    """Test HITL requirement resolution hierarchy."""

    def test_global_true_server_none(self):
        """Server inherits global when hitl_required is None."""
        config = MCPServerConfig(
            transport=MCPTransportType.STDIO,
            command="npx",
            hitl_required=None,
        )
        assert resolve_hitl_requirement(config, global_hitl_required=True) is True

    def test_global_true_server_false(self):
        """Server override takes precedence over global."""
        config = MCPServerConfig(
            transport=MCPTransportType.STDIO,
            command="npx",
            hitl_required=False,
        )
        assert resolve_hitl_requirement(config, global_hitl_required=True) is False

    def test_global_false_server_true(self):
        """Server can require HITL even when global is false."""
        config = MCPServerConfig(
            transport=MCPTransportType.STDIO,
            command="npx",
            hitl_required=True,
        )
        assert resolve_hitl_requirement(config, global_hitl_required=False) is True

    def test_global_false_server_none(self):
        """Server inherits global=False."""
        config = MCPServerConfig(
            transport=MCPTransportType.STDIO,
            command="npx",
            hitl_required=None,
        )
        assert resolve_hitl_requirement(config, global_hitl_required=False) is False
