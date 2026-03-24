"""
MCP Client Manager — Lifecycle management for MCP server connections.

Manages the full lifecycle of MCP server connections:
- Connection establishment (Stdio and Streamable HTTP transports)
- Tool discovery via list_tools()
- Tool invocation with timeout and rate limiting
- Health checks
- Graceful shutdown

Architecture:
    Singleton pattern via module-level functions. Each MCP server gets its own
    AsyncExitStack for isolated lifecycle management. Rate limiting is enforced
    per-server with an in-memory sliding window protected by per-server
    asyncio.Lock to prevent TOCTOU race conditions without cross-server
    contention.

Phase: evolution F2 — MCP Support
Created: 2026-02-28
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from src.core.config import settings
from src.core.constants import (
    MCP_DEFAULT_RATE_LIMIT_CALLS,
    MCP_DEFAULT_RATE_LIMIT_WINDOW,
    MCP_REFERENCE_TOOL_NAME,
)
from src.infrastructure.mcp.schemas import (
    MCPDiscoveredTool,
    MCPServerConfig,
    MCPServerStatus,
    MCPTransportType,
)
from src.infrastructure.mcp.security import validate_server_config
from src.infrastructure.mcp.utils import extract_app_meta
from src.infrastructure.observability.metrics_agents import mcp_server_health

logger = structlog.get_logger(__name__)


class MCPClientManager:
    """
    Manages MCP server connections, tool discovery, and invocation.

    Thread-safety:
        - Per-server asyncio.Lock protects rate limiting from TOCTOU races
        - Each server has independent lifecycle via AsyncExitStack
    """

    def __init__(self) -> None:
        self._servers: dict[str, MCPServerConfig] = {}
        self._sessions: dict[str, ClientSession] = {}
        self._exit_stacks: dict[str, AsyncExitStack] = {}
        self._discovered_tools: dict[str, list[MCPDiscoveredTool]] = {}
        self._reference_content: dict[str, str] = {}  # server_name → read_me content
        self._call_timestamps: dict[str, deque[float]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    # =========================================================================
    # Public read-only accessors (avoid exposing private dicts to callers)
    # =========================================================================

    @property
    def discovered_tools(self) -> dict[str, list[MCPDiscoveredTool]]:
        """Dict of server_name → discovered tools (read-only snapshot)."""
        return dict(self._discovered_tools)

    @property
    def server_configs(self) -> dict[str, MCPServerConfig]:
        """Dict of server_name → config for connected servers (read-only snapshot)."""
        return dict(self._servers)

    @property
    def reference_content(self) -> dict[str, str]:
        """Dict of server_name → read_me reference content (read-only snapshot)."""
        return dict(self._reference_content)

    @property
    def connected_server_count(self) -> int:
        """Number of currently connected MCP servers."""
        return len(self._sessions)

    async def initialize(
        self,
        server_configs: dict[str, MCPServerConfig],
    ) -> None:
        """
        Connect to all enabled MCP servers and discover tools.

        Args:
            server_configs: Dict of server_name → MCPServerConfig
        """
        max_servers = getattr(settings, "mcp_max_servers", 10)
        retry_max = getattr(settings, "mcp_connection_retry_max", 3)

        for i, (name, config) in enumerate(server_configs.items()):
            if i >= max_servers:
                logger.warning(
                    "mcp_max_servers_reached",
                    max_servers=max_servers,
                    total_configured=len(server_configs),
                )
                break

            if not config.enabled:
                logger.info("mcp_server_disabled", server_name=name)
                continue

            # Validate server configuration
            errors = await validate_server_config(config)
            if errors:
                logger.error(
                    "mcp_server_config_invalid",
                    server_name=name,
                    errors=errors,
                )
                mcp_server_health.labels(server_name=name).set(0)
                continue

            self._servers[name] = config
            self._call_timestamps[name] = deque()
            self._locks[name] = asyncio.Lock()

            # Connect with retry
            connected = False
            for attempt in range(retry_max + 1):
                try:
                    await self._connect_server(name, config)
                    connected = True
                    break
                except Exception as e:
                    logger.warning(
                        "mcp_server_connection_attempt_failed",
                        server_name=name,
                        attempt=attempt + 1,
                        max_attempts=retry_max + 1,
                        error=str(e),
                    )
                    if attempt < retry_max:
                        await asyncio.sleep(min(2**attempt, 10))

            if not connected:
                logger.error(
                    "mcp_server_connection_failed",
                    server_name=name,
                    retry_max=retry_max,
                )
                mcp_server_health.labels(server_name=name).set(0)
                continue

            # Discover tools
            try:
                tools = await self.discover_tools(name)
                logger.info(
                    "mcp_server_connected",
                    server_name=name,
                    transport=config.transport.value,
                    tool_count=len(tools),
                    tool_names=[t.tool_name for t in tools],
                )
                mcp_server_health.labels(server_name=name).set(1)
            except Exception as e:
                logger.error(
                    "mcp_tool_discovery_failed",
                    server_name=name,
                    error=str(e),
                )
                mcp_server_health.labels(server_name=name).set(0)

    async def _connect_server(
        self,
        name: str,
        config: MCPServerConfig,
    ) -> None:
        """
        Establish connection to a single MCP server.

        Args:
            name: Server name
            config: Server configuration
        """
        exit_stack = AsyncExitStack()
        await exit_stack.__aenter__()

        try:
            if config.transport == MCPTransportType.STDIO:
                server_params = StdioServerParameters(
                    command=config.command,
                    args=config.args,
                    env=config.env,
                )
                read_stream, write_stream = await exit_stack.enter_async_context(
                    stdio_client(server_params)
                )
            elif config.transport == MCPTransportType.STREAMABLE_HTTP:
                # streamablehttp_client yields (read_stream, write_stream, get_url_fn)
                read_stream, write_stream, _ = await exit_stack.enter_async_context(
                    streamablehttp_client(
                        url=config.url,
                        headers=config.headers or {},
                    )
                )
            else:
                raise ValueError(f"Unsupported transport: {config.transport}")

            # Create and initialize session
            session = await exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()

            self._sessions[name] = session
            self._exit_stacks[name] = exit_stack

        except Exception:
            # Clean up the exit stack on failure
            await exit_stack.__aexit__(None, None, None)
            raise

    async def discover_tools(
        self,
        server_name: str,
    ) -> list[MCPDiscoveredTool]:
        """
        Discover available tools from an MCP server.

        Args:
            server_name: Name of the connected server

        Returns:
            List of discovered tools (limited by mcp_max_tools_per_server)
        """
        session = self._sessions.get(server_name)
        if not session:
            raise RuntimeError(f"MCP server '{server_name}' not connected")

        timeout = getattr(settings, "mcp_tool_timeout_seconds", 30)
        max_tools = getattr(settings, "mcp_max_tools_per_server", 20)

        result = await asyncio.wait_for(
            session.list_tools(),
            timeout=timeout,
        )

        tools: list[MCPDiscoveredTool] = []
        for tool in result.tools[:max_tools]:
            app_resource_uri, app_visibility = extract_app_meta(tool)
            tools.append(
                MCPDiscoveredTool(
                    server_name=server_name,
                    tool_name=tool.name,
                    description=tool.description or "",
                    input_schema=getattr(tool, "inputSchema", None) or {},
                    app_resource_uri=app_resource_uri,
                    app_visibility=app_visibility,
                )
            )

        if len(result.tools) > max_tools:
            logger.warning(
                "mcp_tools_truncated",
                server_name=server_name,
                total_tools=len(result.tools),
                max_tools=max_tools,
            )

        self._discovered_tools[server_name] = tools

        # Auto-fetch read_me content (MCP convention: servers expose a read_me
        # tool providing format reference documentation for the planner).
        await self._fetch_reference_content(server_name, session, tools, timeout)

        return tools

    async def _fetch_reference_content(
        self,
        server_name: str,
        session: ClientSession,
        tools: list[MCPDiscoveredTool],
        timeout: int,
    ) -> None:
        """Auto-fetch read_me tool content for planner prompt injection.

        MCP convention: servers exposing a ``read_me`` tool provide format
        reference documentation. The content is cached per server and injected
        into the planner prompt for better tool argument quality.
        """
        read_me_tool = next((t for t in tools if t.tool_name == MCP_REFERENCE_TOOL_NAME), None)
        if not read_me_tool:
            return

        try:
            result = await asyncio.wait_for(
                session.call_tool(MCP_REFERENCE_TOOL_NAME, {}),
                timeout=timeout,
            )
            if result.content:
                for part in result.content:
                    if hasattr(part, "text") and part.text:
                        self._reference_content[server_name] = part.text
                        logger.info(
                            "mcp_admin_reference_fetched",
                            server_name=server_name,
                            content_chars=len(part.text),
                        )
                        break
        except Exception:
            logger.warning(
                "mcp_admin_reference_fetch_failed",
                server_name=server_name,
                exc_info=True,
            )

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        """
        Call a tool on an MCP server.

        Includes rate limiting enforcement (sliding window per-server)
        with asyncio.Lock protection against TOCTOU race conditions.

        Args:
            server_name: Target server name
            tool_name: Tool to invoke
            arguments: Tool arguments

        Returns:
            Tool result as string

        Raises:
            RuntimeError: If server disconnected, rate limited, or tool error
            asyncio.TimeoutError: If tool execution exceeds timeout
        """
        # Defense in depth: block admin MCP servers disabled by the current user
        from src.core.context import admin_mcp_disabled_ctx

        admin_disabled = admin_mcp_disabled_ctx.get()
        if admin_disabled and server_name in admin_disabled:
            raise RuntimeError(f"MCP server '{server_name}' is disabled for this user")

        session = self._sessions.get(server_name)
        if not session:
            raise RuntimeError(
                f"MCP server '{server_name}' not connected. "
                f"Available: {list(self._sessions.keys())}"
            )

        # Rate limiting with per-server TOCTOU protection
        rate_limit_calls = getattr(settings, "mcp_rate_limit_calls", MCP_DEFAULT_RATE_LIMIT_CALLS)
        rate_limit_window = getattr(
            settings, "mcp_rate_limit_window", MCP_DEFAULT_RATE_LIMIT_WINDOW
        )

        lock = self._locks.get(server_name)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[server_name] = lock

        async with lock:
            timestamps = self._call_timestamps.get(server_name)
            if timestamps is None:
                timestamps = deque()
                self._call_timestamps[server_name] = timestamps

            now = time.monotonic()

            # Purge expired timestamps
            while timestamps and timestamps[0] < now - rate_limit_window:
                timestamps.popleft()

            if len(timestamps) >= rate_limit_calls:
                raise RuntimeError(
                    f"Rate limit exceeded for MCP server '{server_name}': "
                    f"{rate_limit_calls} calls per {rate_limit_window}s"
                )

            timestamps.append(now)

        # Execute tool call with timeout
        timeout = getattr(settings, "mcp_tool_timeout_seconds", 30)
        config = self._servers.get(server_name)
        if config and config.timeout_seconds:
            timeout = config.timeout_seconds

        result = await asyncio.wait_for(
            session.call_tool(tool_name, arguments),
            timeout=timeout,
        )

        # Check for MCP-level errors
        if result.isError:
            error_text = " ".join(c.text for c in result.content if hasattr(c, "text"))
            raise RuntimeError(
                f"MCP tool '{tool_name}' on server '{server_name}' returned error: {error_text}"
            )

        # Parse content
        parts: list[str] = []
        for content in result.content:
            if hasattr(content, "text"):
                parts.append(content.text)
            elif hasattr(content, "data"):
                parts.append("[Binary data]")
            else:
                parts.append(str(content))

        return "\n".join(parts) if parts else ""

    async def read_resource(
        self,
        server_name: str,
        uri: str,
    ) -> str | None:
        """Read a resource from an MCP server (MCP Apps protocol).

        Uses the existing persistent session to fetch HTML content at a
        ``ui://`` URI. Returns ``None`` on any error for graceful degradation
        (caller falls back to standard ``MCP_RESULT`` rendering).

        Handles both ``TextResourceContents`` (text) and
        ``BlobResourceContents`` (base64-encoded binary).

        Args:
            server_name: Target server name.
            uri: Resource URI to read (e.g., ``ui://excalidraw/view``).

        Returns:
            Text content as string, or ``None`` on error.
        """
        # Defense in depth: block admin MCP servers disabled by the current user
        from src.core.context import admin_mcp_disabled_ctx

        admin_disabled = admin_mcp_disabled_ctx.get()
        if admin_disabled and server_name in admin_disabled:
            return None

        session = self._sessions.get(server_name)
        if not session:
            return None

        timeout = getattr(settings, "mcp_tool_timeout_seconds", 30)
        max_size = settings.mcp_app_max_html_size

        try:
            from pydantic import AnyUrl

            result = await asyncio.wait_for(
                session.read_resource(AnyUrl(uri)),
                timeout=timeout,
            )

            for content in result.contents:
                if hasattr(content, "text"):
                    text = content.text
                    if len(text) > max_size:
                        logger.warning(
                            "mcp_read_resource_too_large",
                            server_name=server_name,
                            uri=uri,
                            size=len(text),
                            max_size=max_size,
                        )
                        return None
                    return str(text)
                if hasattr(content, "blob"):
                    import base64

                    decoded = base64.b64decode(content.blob).decode("utf-8", errors="replace")
                    if len(decoded) > max_size:
                        return None
                    return decoded
            return None

        except Exception:
            logger.warning(
                "mcp_read_resource_failed",
                server_name=server_name,
                uri=uri,
                exc_info=True,
            )
            return None

    async def health_check(
        self,
        server_name: str,
    ) -> MCPServerStatus:
        """
        Check health of an MCP server connection.

        Args:
            server_name: Server to check

        Returns:
            MCPServerStatus with connection details
        """
        session = self._sessions.get(server_name)
        if not session:
            return MCPServerStatus(
                server_name=server_name,
                connected=False,
                error="Not connected",
            )

        try:
            timeout = getattr(settings, "mcp_tool_timeout_seconds", 30)
            result = await asyncio.wait_for(
                session.list_tools(),
                timeout=timeout,
            )
            mcp_server_health.labels(server_name=server_name).set(1)
            return MCPServerStatus(
                server_name=server_name,
                connected=True,
                tool_count=len(result.tools),
                last_health_check=datetime.now(UTC).isoformat(),
            )
        except Exception as e:
            mcp_server_health.labels(server_name=server_name).set(0)
            return MCPServerStatus(
                server_name=server_name,
                connected=False,
                error=str(e),
                last_health_check=datetime.now(UTC).isoformat(),
            )

    async def shutdown(self) -> None:
        """Close all MCP server connections gracefully."""
        for name in list(self._exit_stacks.keys()):
            try:
                exit_stack = self._exit_stacks.pop(name)
                await exit_stack.__aexit__(None, None, None)
                logger.info("mcp_server_disconnected", server_name=name)
            except Exception as e:
                logger.error(
                    "mcp_server_shutdown_error",
                    server_name=name,
                    error=str(e),
                )
            finally:
                mcp_server_health.labels(server_name=name).set(0)

        self._sessions.clear()
        self._servers.clear()
        self._discovered_tools.clear()
        self._reference_content.clear()
        self._call_timestamps.clear()
        self._locks.clear()


# =============================================================================
# Module-level Singleton Functions
# =============================================================================

_mcp_manager: MCPClientManager | None = None


def _parse_server_configs() -> dict[str, MCPServerConfig]:
    """
    Parse MCP server configurations from settings.

    Supports two sources (file takes precedence):
    1. mcp_servers_config_path: JSON file path
    2. mcp_servers_config: Inline JSON string

    Returns:
        Dict of server_name → MCPServerConfig
    """
    raw_config: dict[str, Any] = {}

    # Try file first (overrides inline)
    config_path = getattr(settings, "mcp_servers_config_path", None)
    if config_path:
        try:
            path = Path(config_path)
            raw_config = json.loads(path.read_text(encoding="utf-8"))
            logger.info("mcp_config_loaded_from_file", path=config_path)
        except FileNotFoundError:
            logger.error("mcp_config_file_not_found", path=config_path)
            return {}
        except json.JSONDecodeError as e:
            logger.error(
                "mcp_config_file_invalid_json",
                path=config_path,
                error=str(e),
            )
            return {}
    else:
        # Fall back to inline JSON
        inline = getattr(settings, "mcp_servers_config", "{}")
        try:
            raw_config = json.loads(inline)
        except json.JSONDecodeError as e:
            logger.error("mcp_config_inline_invalid_json", error=str(e))
            return {}

    if not raw_config:
        return {}

    # Parse each server config
    configs: dict[str, MCPServerConfig] = {}
    for name, server_data in raw_config.items():
        try:
            configs[name] = MCPServerConfig(**server_data)
        except Exception as e:
            logger.error(
                "mcp_server_config_parse_error",
                server_name=name,
                error=str(e),
            )

    return configs


async def initialize_mcp_client_manager() -> MCPClientManager | None:
    """
    Initialize the MCP client manager singleton.

    Parses configuration, validates servers, establishes connections,
    and discovers tools.

    Returns:
        MCPClientManager instance or None if no valid servers
    """
    global _mcp_manager

    server_configs = _parse_server_configs()
    if not server_configs:
        logger.info("mcp_no_servers_configured")
        return None

    # Filter to enabled servers only
    enabled = {k: v for k, v in server_configs.items() if v.enabled}
    if not enabled:
        logger.info("mcp_no_enabled_servers")
        return None

    manager = MCPClientManager()
    await manager.initialize(enabled)

    # Only keep if at least one server connected
    if manager.connected_server_count == 0:
        logger.warning("mcp_no_servers_connected")
        await manager.shutdown()
        return None

    _mcp_manager = manager
    return manager


def get_mcp_client_manager() -> MCPClientManager | None:
    """Get the MCP client manager singleton (or None if not initialized)."""
    return _mcp_manager


async def cleanup_mcp_client_manager() -> None:
    """Shutdown and cleanup the MCP client manager."""
    global _mcp_manager

    if _mcp_manager is not None:
        await _mcp_manager.shutdown()
        _mcp_manager = None
