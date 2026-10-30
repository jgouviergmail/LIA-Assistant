"""
User MCP Client Pool — Tool metadata cache with ephemeral connections.

Manages discovered tool metadata per (user_id, server_id) with:
- Lazy discovery on first chat request (not background-connect-all)
- Per-key asyncio.Lock to prevent duplicate discovery
- TTL-based eviction of idle entries
- Reference counting to protect active tool calls from eviction
- Per-server rate limiting (sliding window)
- **Ephemeral connections for tool calls**: Each call_tool() creates a fresh
  MCP client (connect → call → close) via the SDK v2 ``Client`` in dual-era
  ``mode="auto"`` (speaks 2026-07-28, falls back to the legacy initialize
  handshake). The SDK's transports use anyio task groups whose cancel scopes
  die when stored in a long-lived pool; ephemeral connections keep the full
  lifecycle within a single async scope, avoiding ClosedResourceError.

Phase: evolution F2.1 — MCP Per-User
Created: 2026-02-28
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Final, NoReturn
from uuid import UUID

import httpx2
import structlog
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from src.core.config import settings
from src.core.constants import (
    MCP_DEFAULT_RATE_LIMIT_CALLS,
    MCP_DEFAULT_RATE_LIMIT_WINDOW,
    MCP_HTTP_READ_TIMEOUT_SECONDS,
    MCP_HTTP_TIMEOUT_SECONDS,
    MCP_REFERENCE_TOOL_NAME,
)
from src.infrastructure.mcp.catalogue_fingerprint import connection_fingerprint
from src.infrastructure.mcp.catalogue_snapshot import (
    CatalogueSnapshot,
    ValidSnapshot,
    catalogue_fingerprint,
    parse_catalogue_snapshot,
    reserve_generation,
    revalidation_horizon_seconds,
    snapshot_routes,
    stored_generation,
)
from src.infrastructure.mcp.declaration_check import (
    DeclarationCheck,
    check_for,
    settle_declaration,
)
from src.infrastructure.mcp.pool_catalogue import (
    Connection,
    DiscoveredCatalogue,
    PoolEntry,
    cache_scope,
    entry_from_snapshot,
    list_every_tool,
    mark_age,
    normalize_tool,
    refresh_reason,
    serves_warm,
    touched,
    ttl_ms,
    warm_entry,
)
from src.infrastructure.mcp.rate_limit import (
    MCPDeclarationChangedError,
    MCPRateLimitError,
    MCPServerCooldown,
    MCPServerFailures,
    MCPServerPausedError,
    MCPToolExecutionError,
    quota_error,
)
from src.infrastructure.mcp.utils import (
    MCPModernOnlyServerError,
    build_client_info,
    is_modern_only_rejection,
    mcp_result_text,
    unwrap_exception_group,
)
from src.infrastructure.observability.metrics_mcp import mcp_catalogue_cache_total

logger = structlog.get_logger(__name__)

#: ``get_or_connect`` called outside a turn's preparation (no stored catalogue given).
NOT_PREPARING: Final = object()


def _surface_root_cause(
    exc: Exception, *, log_event: str, diagnostic_only: bool = False, **log_fields: object
) -> NoReturn:
    """Re-raise the most useful exception out of an anyio failure.

    The MCP SDK's Streamable HTTP transport uses anyio TaskGroups: a sub-task
    failure arrives wrapped in (possibly nested) ExceptionGroups that hide
    the actual error (HTTP 401, connection refused, protocol rejection...).

    - A modern-only server rejection (spec 2026-07-28) becomes
      :class:`MCPModernOnlyServerError` with an actionable message.
    - A single nested root cause is logged and re-raised directly.
    - Anything else propagates unchanged.

    Tool calls have an operation-level diagnostic in their adapter, so their
    transport-unwinding details stay at DEBUG (``diagnostic_only``).
    """
    root = unwrap_exception_group(exc)
    refusal = quota_error(root, settings.mcp_rate_limit_window)
    if refusal is not None:
        raise refusal from exc
    if isinstance(root, MCPToolExecutionError):
        raise root from exc
    if is_modern_only_rejection(root):
        log_refusal = logger.debug if diagnostic_only else logger.warning
        log_refusal(log_event, modern_only_server=True, **log_fields)
        raise MCPModernOnlyServerError() from exc
    if root is not exc and isinstance(root, Exception):
        log_failure = logger.debug if diagnostic_only else logger.error
        log_failure(
            log_event,
            root_error_type=type(root).__name__,
            root_error=str(root),
            **log_fields,
            exc_info=True,
        )
        raise root from exc
    raise exc


@asynccontextmanager
async def _ephemeral_client(
    url: str,
    auth: httpx2.Auth | None,
    extra_headers: dict[str, str] | None = None,
) -> AsyncIterator[Client]:
    """One MCP client for one operation: connect → use → close, single scope.

    ``Client`` defaults to ``mode="auto"`` (dual-era): it speaks protocol
    revision 2026-07-28 and falls back to the legacy ``initialize`` handshake
    for pre-2026 servers. The httpx2 client mirrors the SDK's recommended MCP
    defaults (short connect/write/pool, long read for SSE streams) and carries
    the per-server auth; it is owned here and closed with the scope. It
    follows no redirect itself: the SDK (2.2+) follows one only while it stays
    on the endpoint's origin and keeps the method, and never reads this
    setting — ``follow_redirects=False`` states that same policy.

    ``extra_headers`` are the fixed non-secret headers a plugin's mcp.json
    declares (agent-plugins.org §7.2.1, ADR-225) applied as client default
    headers — auth flows run after request construction, so auth-generated
    headers keep precedence on name collision, exactly the spec's rule.
    """
    async with AsyncExitStack() as stack:
        http_client = await stack.enter_async_context(
            httpx2.AsyncClient(
                follow_redirects=False,
                timeout=httpx2.Timeout(
                    MCP_HTTP_TIMEOUT_SECONDS, read=MCP_HTTP_READ_TIMEOUT_SECONDS
                ),
                auth=auth,
                headers=extra_headers,
            )
        )
        client = await stack.enter_async_context(
            Client(
                streamable_http_client(url, http_client=http_client),
                client_info=build_client_info(),
            )
        )
        yield client


class UserMCPClientPool:
    """
    Tool metadata cache with ephemeral MCP connections.

    Tool discovery (list_tools) is cached per (user_id, server_id) with TTL.
    Tool execution (call_tool) creates a fresh ephemeral connection each time,
    avoiding stale session issues with the MCP SDK's anyio task groups.
    """

    def __init__(
        self,
        cooldowns: MCPServerCooldown | None = None,
        failures: MCPServerFailures | None = None,
    ) -> None:
        self._entries: dict[tuple[UUID, UUID], PoolEntry] = {}
        self._connect_locks: dict[tuple[UUID, UUID], asyncio.Lock] = defaultdict(asyncio.Lock)
        self._rate_locks: dict[tuple[UUID, UUID], asyncio.Lock] = defaultdict(asyncio.Lock)
        self._call_timestamps: dict[tuple[UUID, UUID], deque[float]] = defaultdict(deque)
        self._cooldowns = cooldowns if cooldowns is not None else MCPServerCooldown()
        self._failures = failures if failures is not None else MCPServerFailures()
        # Told when a server's catalogue proved stale at use (spec 2026-10-21 §5.5);
        # installed by the composition root, which owns the revalidation.
        self.on_stale_catalogue: Callable[[UUID, UUID], None] | None = None
        # Network discoveries of this process at once (spec 2026-10-21 §5.3).
        self.discovery_slots = asyncio.Semaphore(settings.mcp_user_preparation_concurrency)

    @property
    def size(self) -> int:
        """Current number of entries in the pool."""
        return len(self._entries)

    async def get_or_connect(
        self,
        user_id: UUID,
        server_id: UUID,
        url: str,
        auth: httpx2.Auth,
        timeout_seconds: int = 30,
        extra_headers: dict[str, str] | None = None,
        force_refresh: bool = False,
        *,
        stored_catalogue: object = NOT_PREPARING,
        on_discovery: Callable[[], None] | None = None,
    ) -> PoolEntry:
        """
        Get existing entry or discover tools from the server.

        Uses per-key asyncio.Lock to prevent duplicate discovery when
        concurrent requests from the same user arrive simultaneously. A server
        that failed to connect is paused (point 29): it raises
        :class:`MCPServerPausedError` until the pause ends, except for the
        manual test (``force_refresh``), and a success clears the pause.

        A turn's preparation passes the row's ``stored_catalogue`` (spec
        2026-10-21 §5.2-5.3): the entry this worker holds for the same
        configuration is served whatever its age (past the server's ``ttlMs``
        it is unverified, checked at use; past the revalidation interval it is
        due for a background revalidation), unless the row carries a newer
        snapshot; else a routable snapshot is hydrated with no I/O; only
        then does the network answer. A discovery holds one of the process's
        ``discovery_slots`` and is bounded by
        ``min(mcp_user_discovery_timeout_seconds, timeout_seconds)``;
        ``on_discovery`` is called once a slot is held, right before it.
        """
        key = (user_id, server_id)
        configuration = connection_fingerprint(url, auth, timeout_seconds, extra_headers)
        connection = Connection(url, auth, timeout_seconds, extra_headers)
        preparing = stored_catalogue is not NOT_PREPARING and not force_refresh

        if preparing:
            # A turn served without the network never queues behind a discovery: a
            # background revalidation holds this key's lock for its whole network
            # wait (fresh review I3 — ADR-366 §3 says the turn never waits for it).
            served = await self._serve_without_network(
                key, configuration, False, stored_catalogue, connection
            )
            if served is not None:
                return touched(served, auth, extra_headers)

        async with self._connect_locks[key]:
            served = (
                warm_entry(self._entries.get(key), configuration, stored_catalogue)
                if preparing
                else await self._serve_without_network(
                    key, configuration, force_refresh, stored_catalogue, connection
                )
            )
            if served is not None:
                return touched(served, auth, extra_headers)

            await self._raise_if_cooling(key)
            if not force_refresh:
                await self._raise_if_paused(key)
            await self._make_room(key)
            generation = reserve_generation()

            # Discover tools via ephemeral connection
            try:
                async with self.discovery_slots:
                    if on_discovery is not None:
                        on_discovery()
                    found = await self._discover_tools(
                        url,
                        auth,
                        min(settings.mcp_user_discovery_timeout_seconds, timeout_seconds),
                        extra_headers=extra_headers,
                    )
            except MCPRateLimitError as exc:
                await self._cooldowns.record(key, exc.retry_after)
                raise
            except Exception:
                pause = await self._failures.record(key)
                logger.info(
                    "user_mcp_server_paused_after_failure",
                    user_id=str(user_id),
                    server_id=str(server_id),
                    pause_seconds=pause,
                )
                raise
            await self._failures.clear(key)
            entry = PoolEntry(
                user_id=user_id,
                server_id=server_id,
                last_used=time.monotonic(),
                url=url,
                auth=auth,
                extra_headers=extra_headers,
                timeout_seconds=timeout_seconds,
                tools=found.tools,
                discovered_at=time.monotonic(),
                catalogue_fingerprint=catalogue_fingerprint(found.tools),
                configuration_fingerprint=configuration,
                has_reference_tool=found.has_reference_tool,
                server_ttl_ms=found.server_ttl_ms,
                cache_scope=found.cache_scope,
                server_instructions=found.server_instructions,
                generation=generation,
            )
            self._entries[key] = entry

            logger.info(
                "user_mcp_pool_connected",
                user_id=str(user_id),
                server_id=str(server_id),
                pool_size=len(self._entries),
                tool_count=len(entry.tools),
                has_reference_tool=found.has_reference_tool,
                listing=found.outcome,
            )

            return entry

    def hydrate(
        self,
        *,
        user_id: UUID,
        server_id: UUID,
        url: str,
        auth: httpx2.Auth | None,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None,
        snapshot: CatalogueSnapshot,
        verified: bool,
    ) -> PoolEntry:
        """Install the entry a persisted snapshot stands for — no I/O (spec 2026-10-21 §5.2).

        Args:
            user_id: The account.
            server_id: The server.
            url: The row's URL.
            auth: The auth built for the row.
            timeout_seconds: The row's tool timeout.
            extra_headers: The row's fixed headers.
            snapshot: A snapshot routable for this configuration.
            verified: False once it is past its revalidation age.

        Returns:
            The installed entry.
        """
        entry = entry_from_snapshot(
            snapshot,
            user_id=user_id,
            server_id=server_id,
            url=url,
            auth=auth,
            timeout_seconds=timeout_seconds,
            extra_headers=extra_headers,
            verified=verified,
        )
        self._entries[(user_id, server_id)] = entry
        return entry

    async def pause_remaining(self, user_id: UUID, server_id: UUID) -> float:
        """Seconds left in the server's failure pause (0 when it is not paused)."""
        return await self._failures.remaining((user_id, server_id))

    async def _serve_without_network(
        self,
        key: tuple[UUID, UUID],
        configuration: str,
        force_refresh: bool,
        stored: object,
        connection: Connection,
    ) -> PoolEntry | None:
        """The entry a turn can use without the network, or None."""
        if stored is NOT_PREPARING:
            return (
                self._entries[key] if self._cache_hit(key, configuration, force_refresh) else None
            )
        if force_refresh:
            return None
        entry = self._entries.get(key)
        if entry is not None and serves_warm(entry, configuration, stored_generation(stored)):
            mcp_catalogue_cache_total.labels(result="hit").inc()
            mark_age(entry, time.monotonic() - entry.discovered_at)
            return entry
        read = parse_catalogue_snapshot(stored)
        if not (
            isinstance(read, ValidSnapshot)
            and snapshot_routes(read, configuration_fingerprint=configuration)
        ):
            mcp_catalogue_cache_total.labels(
                result="miss" if entry is None else "configuration"
            ).inc()
            return None
        await self._raise_if_cooling(key)
        await self._raise_if_paused(key)
        await self._make_room(key)
        # Awaited outside the lock: a discovery may have installed the server's CURRENT
        # catalogue meanwhile — an older snapshot never replaces it (third fresh review).
        fresher = warm_entry(self._entries.get(key), configuration, stored)
        if fresher is not None:
            mcp_catalogue_cache_total.labels(result="hit").inc()
            return fresher
        mcp_catalogue_cache_total.labels(result="snapshot").inc()
        snapshot = read.snapshot
        age = snapshot.age_seconds(datetime.now(UTC))
        hydrated = self.hydrate(
            user_id=key[0],
            server_id=key[1],
            url=connection.url,
            auth=connection.auth,
            timeout_seconds=connection.timeout_seconds,
            extra_headers=connection.extra_headers,
            snapshot=snapshot,
            verified=age < revalidation_horizon_seconds(snapshot),
        )
        mark_age(hydrated, age)
        return hydrated

    async def _make_room(self, key: tuple[UUID, UUID]) -> None:
        """Respect the global pool limit before adding an entry."""
        max_total = settings.mcp_user_pool_max_total
        while key not in self._entries and len(self._entries) >= max_total:
            evicted = await self._evict_oldest_idle()
            if not evicted:
                raise RuntimeError(
                    f"User MCP pool is full ({max_total} entries) "
                    "and no idle entries available for eviction"
                )

    def _cache_hit(self, key: tuple[UUID, UUID], configuration: str, force_refresh: bool) -> bool:
        entry = self._entries.get(key)
        if entry is None:
            mcp_catalogue_cache_total.labels(result="miss").inc()
            return False
        reason = refresh_reason(entry, configuration, force_refresh)
        if reason is None:
            mcp_catalogue_cache_total.labels(result="hit").inc()
            return True
        mcp_catalogue_cache_total.labels(result=reason).inc()
        return False

    async def call_tool(
        self,
        user_id: UUID,
        server_id: UUID,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_seconds: int = 30,
        *,
        built_from: str | None = None,
        declaration: Mapping[str, Any] | None = None,
    ) -> str:
        """
        Execute a tool call via an ephemeral MCP connection.

        Creates a fresh connection (connect → initialize → call_tool → close)
        for each invocation. This avoids stale session issues where the MCP
        SDK's anyio background tasks die between pool creation and tool call.

        A call is checked first, in the same session (spec 2026-10-21 §5.5), when
        the entry is past its server's freshness (``catalogue_verified`` false) or
        when the call was built from ANOTHER catalogue than the entry holds now (a
        revalidation replaced it mid-turn — fresh review 2026-10-29): a call the
        current declaration no longer admits raises
        :class:`MCPDeclarationChangedError` unsent; a listing that differs from the
        entry's catalogue schedules a revalidation; an equal one verifies it.

        Args:
            built_from: The catalogue fingerprint the calling adapter was built from.
            declaration: The tool's declaration the call was built from.
        """
        key = (user_id, server_id)
        entry = self._entries.get(key)
        if not entry:
            raise RuntimeError(f"No pool entry for user={user_id}, server={server_id}")

        await self._raise_if_cooling(key)

        # Rate limiting (per-server sliding window)
        await self._check_rate_limit(key)

        check = check_for(entry, tool_name, arguments, built_from, declaration)
        # Increment reference counter (eviction protection)
        entry.active_calls += 1
        try:
            result = await self._execute_call_ephemeral(
                url=entry.url,
                auth=entry.auth,
                tool_name=tool_name,
                arguments=arguments,
                timeout_seconds=timeout_seconds,
                extra_headers=entry.extra_headers,
                declaration=check,
            )
            entry.last_used = time.monotonic()
            if check is not None:
                settle_declaration(entry, check, check.verdict, self.on_stale_catalogue)
            return result
        except MCPDeclarationChangedError as changed:
            settle_declaration(entry, check, changed.reason, self.on_stale_catalogue)
            raise
        except MCPRateLimitError as exc:
            await self._cooldowns.record(key, exc.retry_after)
            raise
        finally:
            entry.active_calls = max(0, entry.active_calls - 1)

    async def fetch_reference(
        self, user_id: UUID, server_id: UUID, timeout_seconds: int
    ) -> str | None:
        """Call a server's ``read_me`` over one ephemeral session (spec 2026-10-21 §5.5b).

        The pool's own call path: cooling, rate limit and eviction protection
        apply, and a server error is an error, never a reference.

        Args:
            user_id: The account.
            server_id: The server, already in the pool.
            timeout_seconds: The bound of the whole call.

        Returns:
            The reference text, or None when the answer carries none.

        Raises:
            Exception: Whatever the call raised (``TimeoutError`` past the bound).
        """
        text = await self.call_tool(
            user_id, server_id, MCP_REFERENCE_TOOL_NAME, {}, timeout_seconds=timeout_seconds
        )
        return text or None

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

        provider_called = False
        try:
            await self._raise_if_cooling(key)
            provider_called = True
            return await self._execute_read_resource_ephemeral(
                url=entry.url,
                auth=entry.auth,
                uri=uri,
                timeout_seconds=timeout_seconds,
                extra_headers=entry.extra_headers,
            )
        except MCPRateLimitError as exc:
            # Re-reading a known deadline must not extend it by rounded seconds.
            if provider_called:
                await self._cooldowns.record(key, exc.retry_after)
            logger.info(
                "user_mcp_read_resource_rate_limited",
                user_id=str(user_id),
                server_id=str(server_id),
                retry_after=exc.retry_after,
            )
            return None
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
        auth: httpx2.Auth | None,
        uri: str,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> str | None:
        """Read a resource via an ephemeral MCP connection.

        Same ephemeral lifecycle pattern as ``_execute_call_ephemeral``:
        connect → read_resource → close, all within a single async scope
        bounded by ``timeout_seconds``.
        """
        max_size = settings.mcp_app_max_html_size

        async def _inner() -> str | None:
            async with _ephemeral_client(url, auth, extra_headers) as client:
                result = await client.read_resource(uri)

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
            _surface_root_cause(
                exc,
                log_event="mcp_ephemeral_read_resource_failed",
                uri=uri,
                url=url,
            )

    async def disconnect(self, user_id: UUID, server_id: UUID) -> None:
        """Remove a server entry and clean up associated resources.

        Editing, toggling or re-authorising a server disconnects it, so its
        failure pause goes too (point 29): the new configuration deserves a
        fresh try. A quota cooldown stays — the provider declared it.
        """
        key = (user_id, server_id)
        entry = self._entries.pop(key, None)

        # Clean up per-key resources to prevent memory leaks
        self._connect_locks.pop(key, None)
        self._rate_locks.pop(key, None)
        self._call_timestamps.pop(key, None)
        self._cooldowns.forget_local(key)
        await self._failures.clear(key)

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

    async def _raise_if_cooling(self, key: tuple[UUID, UUID]) -> None:
        remaining = await self._cooldowns.remaining(key)
        if remaining > 0:
            raise MCPRateLimitError(remaining)

    async def _raise_if_paused(self, key: tuple[UUID, UUID]) -> None:
        remaining = await self._failures.remaining(key)
        if remaining > 0:
            raise MCPServerPausedError(remaining)

    @staticmethod
    async def _discover_tools(
        url: str,
        auth: httpx2.Auth | None,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> DiscoveredCatalogue:
        """Discover a server's catalogue via an ephemeral connection (connect → list → close).

        The whole discovery (connect, every ``tools/list`` page) is bounded by
        ``timeout_seconds`` via ``asyncio.wait_for`` so an unresponsive server
        cannot hang silently. It never calls ``read_me``: the reference is read
        at real use (spec 2026-10-21 §5.5b).

        Returns:
            The tools in canonical order, with what the server said about its
            list (``ttlMs``, ``cacheScope``), its handshake instructions, and
            whether it exposes ``read_me``.
        """

        async def _inner() -> DiscoveredCatalogue:
            async with _ephemeral_client(url, auth, extra_headers) as client:
                listed, first, outcome = await list_every_tool(client)
                instructions = getattr(client, "instructions", None)
            tools = sorted((normalize_tool(tool) for tool in listed), key=lambda t: t["name"])
            return DiscoveredCatalogue(
                tools=tools,
                has_reference_tool=any(t["name"] == MCP_REFERENCE_TOOL_NAME for t in tools),
                server_ttl_ms=ttl_ms(first),
                cache_scope=cache_scope(first),
                server_instructions=instructions if isinstance(instructions, str) else None,
                outcome=outcome,
            )

        try:
            return await asyncio.wait_for(_inner(), timeout=timeout_seconds)
        except Exception as exc:
            # Discovery is the test-connection path: its error string is what
            # the user reads in the settings screen — surface the root cause.
            _surface_root_cause(exc, log_event="mcp_ephemeral_discovery_failed", url=url)

    @staticmethod
    async def _execute_call_ephemeral(
        url: str,
        auth: httpx2.Auth | None,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
        declaration: DeclarationCheck | None = None,
    ) -> str:
        """Execute a tool call via an ephemeral MCP connection.

        Creates a fresh connection, calls the tool, and closes — all within a
        single async scope. This ensures the MCP SDK's anyio background tasks
        stay alive for the entire duration of the call.

        The entire lifecycle (connect + call_tool) is bounded by
        timeout_seconds via asyncio.wait_for to prevent silent hangs when a
        server is unresponsive during connection or handshake.
        """

        async def _inner() -> str:
            async with _ephemeral_client(url, auth, extra_headers) as client:
                logger.debug(
                    "mcp_ephemeral_call_tool_args",
                    tool_name=tool_name,
                    arg_keys=list(arguments.keys()),
                )
                if declaration is not None:
                    await declaration.verify(client)

                result = await client.call_tool(tool_name, arguments)

                # Parse result content
                if result.is_error:
                    error_text = "\n".join(c.text for c in result.content if hasattr(c, "text"))
                    raise MCPToolExecutionError(f"MCP tool error: {error_text}")

                result_text = mcp_result_text(result)
            return result_text

        try:
            return await asyncio.wait_for(_inner(), timeout=timeout_seconds)
        except Exception as exc:
            _surface_root_cause(
                exc,
                log_event="mcp_ephemeral_call_failed",
                diagnostic_only=True,
                tool_name=tool_name,
                url=url,
            )

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
                raise MCPRateLimitError(window - (now - timestamps[0]))

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
