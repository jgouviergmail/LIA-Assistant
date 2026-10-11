"""
MCP Security Module.

Provides security validation for MCP server configurations:
- Server configuration validation (transport-specific checks)
- SSRF prevention for HTTP endpoints (IP blocklists, hostname checks)
- HITL requirement resolution (per-server > global hierarchy)

Architecture:
    Separated from client_manager.py (SRP). Prepares for future per-user
    MCP server management (Feature 2.1).

    Address policy and the IP predicate belong to infrastructure/utils/url_validation.py,
    shared with web fetch and the skill library without a domain dependency.

Phase: evolution F2 — MCP Support
Created: 2026-02-28
"""

from __future__ import annotations

import asyncio
import socket
from urllib.parse import urlparse

import structlog

from src.infrastructure.mcp.schemas import MCPServerConfig, MCPTransportType
from src.infrastructure.utils.url_validation import (
    _BLOCKED_HOSTNAME_SUFFIXES as _BLOCKED_HOSTNAME_SUFFIXES,
)
from src.infrastructure.utils.url_validation import (
    _BLOCKED_HOSTNAMES as _BLOCKED_HOSTNAMES,
)
from src.infrastructure.utils.url_validation import (
    _BLOCKED_IP_NETWORKS as _BLOCKED_IP_NETWORKS,
)
from src.infrastructure.utils.url_validation import (
    check_ip_safety as _check_ip_safety,
)

logger = structlog.get_logger(__name__)


async def validate_http_endpoint(url: str) -> tuple[bool, str | None]:
    """
    Validate an HTTP MCP endpoint URL for SSRF safety.

    Checks:
    - URL scheme is HTTPS (HTTP blocked for security)
    - Hostname not in blocklist
    - Resolved IP not in blocked network ranges
    - IPv4-mapped IPv6 addresses properly normalized

    Args:
        url: The endpoint URL to validate

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL: {e}"

    # Scheme must be HTTPS
    if parsed.scheme != "https":
        return False, f"MCP HTTP endpoint must use HTTPS, got '{parsed.scheme}'"

    hostname = parsed.hostname
    if not hostname:
        return False, "URL has no hostname"

    # Check hostname blocklist
    hostname_lower = hostname.lower()
    if hostname_lower in _BLOCKED_HOSTNAMES:
        return False, f"Blocked hostname: {hostname}"

    if any(hostname_lower.endswith(suffix) for suffix in _BLOCKED_HOSTNAME_SUFFIXES):
        return False, f"Blocked hostname suffix: {hostname}"

    # Resolve DNS and check IP safety (async to avoid blocking the event loop)
    try:
        loop = asyncio.get_running_loop()
        addrinfos = await loop.getaddrinfo(
            hostname, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
        )
    except socket.gaierror as e:
        return False, f"DNS resolution failed for {hostname}: {e}"

    if not addrinfos:
        return False, f"No DNS records found for {hostname}"

    for addrinfo in addrinfos:
        ip_str = addrinfo[4][0]
        if not _check_ip_safety(ip_str):
            return False, f"Blocked IP address: {ip_str} (resolved from {hostname})"

    return True, None


async def validate_server_config(config: MCPServerConfig) -> list[str]:
    """
    Validate an MCP server configuration.

    Checks transport-specific requirements and security constraints.

    Args:
        config: MCP server configuration to validate

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []

    if config.transport == MCPTransportType.STDIO:
        if not config.command:
            errors.append("Stdio transport requires 'command'")
        elif "/" in config.command or "\\" in config.command:
            # Prevent path traversal in command names
            errors.append(
                f"Command must be a program name, not a path: '{config.command}'. "
                f"Use 'args' for path arguments."
            )

    elif config.transport == MCPTransportType.STREAMABLE_HTTP:
        if not config.url:
            errors.append("Streamable HTTP transport requires 'url'")
        elif not config.internal:
            is_valid, error = await validate_http_endpoint(config.url)
            if not is_valid:
                errors.append(f"HTTP endpoint validation failed: {error}")
        # internal=True: skip SSRF validation (trusted Docker-internal service)

    if errors:
        logger.warning(
            "mcp_server_config_validation_failed",
            transport=config.transport.value,
            errors=errors,
        )

    return errors


def resolve_hitl_requirement(
    server_config: MCPServerConfig,
    global_hitl_required: bool,
) -> bool:
    """
    Resolve HITL requirement with per-server override.

    Hierarchy: per-server hitl_required > global MCP_HITL_REQUIRED.

    Args:
        server_config: MCP server configuration (may have hitl_required=None)
        global_hitl_required: Global MCP_HITL_REQUIRED setting

    Returns:
        Whether HITL approval is required for tools from this server
    """
    if server_config.hitl_required is not None:
        return server_config.hitl_required
    return global_hitl_required
