"""
User MCP Client Pool — Tool metadata cache with ephemeral connections.

Manages discovered tool metadata per (user_id, server_id) with:
- Lazy discovery on first chat request (not background-connect-all)
- Per-key asyncio.Lock to prevent duplicate discovery
- TTL-based eviction of idle entries
- Reference counting to protect active tool calls from eviction
- Per-server rate limiting (sliding window)
- **Ephemeral connections for tool calls**: Each call_tool() creates a fresh
  MCP session (connect → initialize → call → close). The MCP Python SDK's
  streamablehttp_client uses anyio task groups whose cancel scopes die when
  stored in a long-lived pool. Ephemeral connections keep the full lifecycle
  within a single async scope, avoiding ClosedResourceError / CancelledError.

Phase: evolution F2.1 — MCP Per-User
Created: 2026-02-28
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx
import structlog
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from src.core.config import settings
from src.core.constants import (
    MCP_DEFAULT_RATE_LIMIT_CALLS,
    MCP_DEFAULT_RATE_LIMIT_WINDOW,
    MCP_REFERENCE_TOOL_NAME,
)
from src.infrastructure.mcp.utils import extract_app_meta

logger = structlog.get_logger(__name__)


@dataclass
class PoolEntry:
    """Tool metadata for a connected user MCP server (no persistent session)."""

    user_id: UUID
    server_id: UUID
    last_used: float
    url: str = ""
    auth: httpx.Auth | None = None
    timeout_seconds: int = 30
    tools: list[dict[str, Any]] = field(default_factory=list)
    active_calls: int = 0  # Reference counter — prevents eviction during active tool calls
    reference_content: str | None = None  # Auto-fetched read_me content (cached per entry)


class UserMCPClientPool:
    """
    Tool metadata cache with ephemeral MCP connections.

    Tool discovery (list_tools) is cached per (user_id, server_id) with TTL.
    Tool execution (call_tool) creates a fresh ephemeral connection each time,
    avoiding stale session issues with the MCP SDK's anyio task groups.
    """

    def __init__(self) -> None:
        self._entries: dict[tuple[UUID, UUID], PoolEntry] = {}
        self._connect_locks: dict[tuple[UUID, UUID], asyncio.Lock] = defaultdict(asyncio.Lock)
        self._rate_locks: dict[tuple[UUID, UUID], asyncio.Lock] = defaultdict(asyncio.Lock)
        self._call_timestamps: dict[tuple[UUID, UUID], deque[float]] = defaultdict(deque)

    @property
    def size(self) -> int:
        """Current number of entries in the pool."""
        return len(self._entries)

    async def get_or_connect(
        self,
        user_id: UUID,
        server_id: UUID,
        url: str,
        auth: httpx.Auth,
        timeout_seconds: int = 30,
    ) -> PoolEntry:
        """
        Get existing entry or discover tools from the server.

        Uses per-key asyncio.Lock to prevent duplicate discovery when
        concurrent requests from the same user arrive simultaneously.
        """
        key = (user_id, server_id)

        async with self._connect_locks[key]:
            if key in self._entries:
                # Update auth in case tokens were refreshed
                self._entries[key].auth = auth
                self._entries[key].last_used = time.monotonic()
                return self._entries[key]

            # Check global pool limit
            max_total = settings.mcp_user_pool_max_total
            while len(self._entries) >= max_total:
                evicted = await self._evict_oldest_idle()
                if not evicted:
                    raise RuntimeError(
                        f"User MCP pool is full ({max_total} entries) "
                        "and no idle entries available for eviction"
                    )

            # Discover tools via ephemeral connection
            tools, reference_content = await self._discover_tools(url, auth, timeout_seconds)
            entry = PoolEntry(
                user_id=user_id,
                server_id=server_id,
                last_used=time.monotonic(),
                url=url,
                auth=auth,
                timeout_seconds=timeout_seconds,
                tools=tools,
                reference_content=reference_content,
            )
            self._entries[key] = entry

            logger.info(
                "user_mcp_pool_connected",
                user_id=str(user_id),
                server_id=str(server_id),
                pool_size=len(self._entries),
                tool_count=len(entry.tools),
                has_reference_content=reference_content is not None,
            )

            return entry

    async def call_tool(
        self,
        user_id: UUID,
        server_id: UUID,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_seconds: int = 30,
    ) -> str:
        """
        Execute a tool call via an ephemeral MCP connection.

        Creates a fresh connection (connect → initialize → call_tool → close)
        for each invocation. This avoids stale session issues where the MCP
        SDK's anyio background tasks die between pool creation and tool call.
        """
        key = (user_id, server_id)
        entry = self._entries.get(key)
        if not entry:
            raise RuntimeError(f"No pool entry for user={user_id}, server={server_id}")

        # Rate limiting (per-server sliding window)
        await self._check_rate_limit(key)

        # Increment reference counter (eviction protection)
        entry.active_calls += 1
        try:
            result = await self._execute_call_ephemeral(
                url=entry.url,
                auth=entry.auth,
                tool_name=tool_name,
                arguments=arguments,
                timeout_seconds=timeout_seconds,
            )
            entry.last_used = time.monotonic()
            return result
        finally:
            entry.active_calls = max(0, entry.active_calls - 1)

    async def read_resource(
        self,
        user_id: UUID,
        server_id: UUID,
        uri: str,
        timeout_seconds: int = 30,
    ) -> str | None:
        """Read a resource via an ephemeral MCP connection (MCP Apps protocol).

        Returns ``None`` on any error for graceful degradation (caller falls
        back to standard ``MCP_RESULT`` rendering).

        Args:
            user_id: User identifier.
            server_id: MCP server identifier.
            uri: Resource URI to read (e.g., ``ui://excalidraw/view``).
            timeout_seconds: Timeout for the ephemeral connection.

        Returns:
            Text content as string, or ``None`` on error.
        """
        key = (user_id, server_id)
        entry = self._entries.get(key)
        if not entry:
            return None

        try:
            return await self._execute_read_resource_ephemeral(
                url=entry.url,
                auth=entry.auth,
                uri=uri,
                timeout_seconds=timeout_seconds,
            )
        except Exception:
            logger.warning(
                "user_mcp_read_resource_failed",
                user_id=str(user_id),
                server_id=str(server_id),
                uri=uri,
                exc_info=True,
            )
            return None

    @staticmethod
    async def _execute_read_resource_ephemeral(
        url: str,
        auth: httpx.Auth | None,
        uri: str,
        timeout_seconds: int,
    ) -> str | None:
        """Read a resource via an ephemeral MCP connection.

        Same ephemeral lifecycle pattern as ``_execute_call_ephemeral``:
        connect → initialize → read_resource → close, all within a single
        async scope bounded by ``timeout_seconds``.
        """
        max_size = settings.mcp_app_max_html_size

        async def _inner() -> str | None:
            async with AsyncExitStack() as exit_stack:
                read_stream, write_stream, _ = await exit_stack.enter_async_context(
                    streamablehttp_client(url=url, auth=auth)
                )
                session = await exit_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                await session.initialize()

                from pydantic import AnyUrl

                result = await session.read_resource(AnyUrl(uri))

                for content in result.contents:
                    if hasattr(content, "text"):
                        text = content.text
                        if len(text) > max_size:
                            return None
                        return str(text)
                    if hasattr(content, "blob"):
                        import base64

                        decoded = base64.b64decode(content.blob).decode("utf-8", errors="replace")
                        if len(decoded) > max_size:
                            return None
                        return decoded
            return None

        try:
            return await asyncio.wait_for(_inner(), timeout=timeout_seconds)
        except Exception as exc:
            # Unwrap ExceptionGroup from anyio TaskGroup (same as _execute_call_ephemeral)
            if isinstance(exc, ExceptionGroup):
                sub_exceptions = exc.exceptions
                logger.error(
                    "mcp_ephemeral_read_resource_exception_group",
                    uri=uri,
                    url=url,
                    sub_exception_count=len(sub_exceptions),
                    sub_exceptions=[
                        {"type": type(se).__name__, "message": str(se)} for se in sub_exceptions
                    ],
                    exc_info=True,
                )
                if len(sub_exceptions) == 1:
                    raise sub_exceptions[0] from exc
            raise

    async def disconnect(self, user_id: UUID, server_id: UUID) -> None:
        """Remove a server entry and clean up associated resources."""
        key = (user_id, server_id)
        entry = self._entries.pop(key, None)

        # Clean up per-key resources to prevent memory leaks
        self._connect_locks.pop(key, None)
        self._rate_locks.pop(key, None)
        self._call_timestamps.pop(key, None)

        if entry:
            logger.info(
                "user_mcp_pool_disconnected",
                user_id=str(user_id),
                server_id=str(server_id),
                pool_size=len(self._entries),
            )

    async def disconnect_user(self, user_id: UUID) -> None:
        """Disconnect all servers for a specific user."""
        keys_to_remove = [k for k in self._entries if k[0] == user_id]
        for key in keys_to_remove:
            await self.disconnect(*key)

    async def evict_idle(self) -> int:
        """
        Remove idle entries that have exceeded TTL.

        IMPORTANT: Never evicts entries with active_calls > 0.
        """
        ttl = settings.mcp_user_pool_ttl_seconds
        now = time.monotonic()
        evicted = 0

        keys_to_evict = [
            key
            for key, entry in self._entries.items()
            if (now - entry.last_used) > ttl and entry.active_calls == 0
        ]

        for key in keys_to_evict:
            await self.disconnect(*key)
            evicted += 1

        if evicted > 0:
            logger.info(
                "user_mcp_pool_evicted_idle",
                evicted_count=evicted,
                remaining=len(self._entries),
            )

        return evicted

    async def shutdown(self) -> None:
        """Shutdown the pool and remove all entries."""
        keys = list(self._entries.keys())
        for key in keys:
            await self.disconnect(*key)

        self._connect_locks.clear()
        self._rate_locks.clear()
        self._call_timestamps.clear()

        logger.info("user_mcp_pool_shutdown_complete")

    # =========================================================================
    # Private helpers
    # =========================================================================

    @staticmethod
    async def _discover_tools(
        url: str,
        auth: httpx.Auth | None,
        timeout_seconds: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Discover tools via an ephemeral MCP connection (connect → list → close).

        The entire discovery (connect + initialize + list_tools + optional read_me)
        is bounded by timeout_seconds via asyncio.wait_for to prevent silent hangs
        when a server is unresponsive during connection or handshake.

        Returns:
            Tuple of (tools_list, reference_content). reference_content is the
            result of calling the server's ``read_me`` tool (if it exists),
            or None if not available. This content is cached in PoolEntry and
            injected into the planner prompt for better parameter generation.
        """

        async def _inner() -> tuple[list[dict[str, Any]], str | None]:
            async with AsyncExitStack() as exit_stack:
                read_stream, write_stream, _ = await exit_stack.enter_async_context(
                    streamablehttp_client(url=url, auth=auth)
                )
                session = await exit_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                await session.initialize()

                tools_result = await session.list_tools()

                max_tools = settings.mcp_max_tools_per_server
                tools_list = []
                for tool in (tools_result.tools or [])[:max_tools]:
                    app_resource_uri, app_visibility = extract_app_meta(tool)
                    tools_list.append(
                        {
                            "name": tool.name,
                            "description": tool.description or "",
                            "input_schema": getattr(tool, "inputSchema", None) or {},
                            "app_resource_uri": app_resource_uri,
                            "app_visibility": app_visibility,
                        }
                    )

                # Auto-inject: detect and call read_me tool (MCP convention).
                # Reference tools provide format documentation that the planner
                # needs to generate correct parameters (e.g., Excalidraw elements).
                reference_content: str | None = None
                read_me_tool = next(
                    (t for t in (tools_result.tools or []) if t.name == MCP_REFERENCE_TOOL_NAME),
                    None,
                )
                if read_me_tool:
                    try:
                        read_me_result = await session.call_tool(MCP_REFERENCE_TOOL_NAME, {})
                        if read_me_result.content:
                            for part in read_me_result.content:
                                if hasattr(part, "text") and part.text:
                                    reference_content = part.text
                                    break
                    except Exception as exc:
                        logger.debug(
                            "user_mcp_reference_fetch_failed",
                            url=url,
                            error=str(exc),
                        )

            return tools_list, reference_content

        return await asyncio.wait_for(_inner(), timeout=timeout_seconds)

    @staticmethod
    async def _execute_call_ephemeral(
        url: str,
        auth: httpx.Auth | None,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_seconds: int,
    ) -> str:
        """Execute a tool call via an ephemeral MCP connection.

        Creates a fresh connection, initializes, calls the tool, and closes —
        all within a single async scope. This ensures the MCP SDK's anyio
        background tasks stay alive for the entire duration of the call.

        The entire lifecycle (connect + initialize + call_tool) is bounded by
        timeout_seconds via asyncio.wait_for to prevent silent hangs when a
        server is unresponsive during connection or handshake.
        """

        async def _inner() -> str:
            async with AsyncExitStack() as exit_stack:
                read_stream, write_stream, _ = await exit_stack.enter_async_context(
                    streamablehttp_client(url=url, auth=auth)
                )
                session = await exit_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                await session.initialize()

                logger.debug(
                    "mcp_ephemeral_call_tool_args",
                    tool_name=tool_name,
                    arg_keys=list(arguments.keys()),
                )

                result = await session.call_tool(tool_name, arguments)

                # Parse result content
                if result.isError:
                    error_text = "\n".join(c.text for c in result.content if hasattr(c, "text"))
                    raise RuntimeError(f"MCP tool error: {error_text}")

                result_text = "\n".join(c.text for c in result.content if hasattr(c, "text"))
            return result_text

        try:
            return await asyncio.wait_for(_inner(), timeout=timeout_seconds)

        except Exception as exc:
            # Unwrap ExceptionGroup from anyio TaskGroup to expose root cause.
            # The MCP SDK's streamablehttp_client uses anyio TaskGroups internally;
            # when a sub-task fails, anyio wraps it in ExceptionGroup which hides
            # the actual error (e.g., HTTP 401, connection refused, etc.).
            # Note: ExceptionGroup inherits from Exception in Python 3.11+.
            if isinstance(exc, ExceptionGroup):
                sub_exceptions = exc.exceptions
                logger.error(
                    "mcp_ephemeral_call_exception_group",
                    tool_name=tool_name,
                    url=url,
                    sub_exception_count=len(sub_exceptions),
                    sub_exceptions=[
                        {
                            "type": type(se).__name__,
                            "message": str(se),
                        }
                        for se in sub_exceptions
                    ],
                    exc_info=True,
                )
                # Re-raise the first sub-exception for cleaner error handling
                if len(sub_exceptions) == 1:
                    raise sub_exceptions[0] from exc
            raise

    async def _evict_oldest_idle(self) -> bool:
        """Evict the oldest idle entry. Returns True if one was evicted."""
        idle_entries = [
            (key, entry) for key, entry in self._entries.items() if entry.active_calls == 0
        ]

        if not idle_entries:
            return False

        # Find the oldest
        oldest_key, _ = min(idle_entries, key=lambda x: x[1].last_used)
        await self.disconnect(*oldest_key)
        return True

    async def _check_rate_limit(self, key: tuple[UUID, UUID]) -> None:
        """Enforce per-server rate limiting (sliding window)."""
        max_calls = getattr(settings, "mcp_rate_limit_calls", MCP_DEFAULT_RATE_LIMIT_CALLS)
        window = getattr(settings, "mcp_rate_limit_window", MCP_DEFAULT_RATE_LIMIT_WINDOW)

        async with self._rate_locks[key]:
            timestamps = self._call_timestamps[key]
            now = time.monotonic()

            # Remove expired timestamps
            while timestamps and (now - timestamps[0]) > window:
                timestamps.popleft()

            if len(timestamps) >= max_calls:
                raise RuntimeError(f"MCP rate limit exceeded: {max_calls} calls per {window}s")

            timestamps.append(now)


# =============================================================================
# Module-level singleton
# =============================================================================

_user_pool: UserMCPClientPool | None = None


def get_user_mcp_pool() -> UserMCPClientPool | None:
    """Get the user MCP pool singleton (None if not initialized)."""
    return _user_pool


async def initialize_user_mcp_pool() -> UserMCPClientPool:
    """Initialize the user MCP pool singleton."""
    global _user_pool
    _user_pool = UserMCPClientPool()

    logger.info(
        "user_mcp_pool_initialized",
        max_total=settings.mcp_user_pool_max_total,
        ttl_seconds=settings.mcp_user_pool_ttl_seconds,
    )

    return _user_pool


async def cleanup_user_mcp_pool() -> None:
    """Shutdown and cleanup the user MCP pool singleton."""
    global _user_pool
    if _user_pool:
        await _user_pool.shutdown()
        _user_pool = None
        logger.info("user_mcp_pool_cleaned_up")
