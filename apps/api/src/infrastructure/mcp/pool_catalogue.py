"""What the personal-MCP pool holds about one server, and how it is built.

Extracted from ``user_pool`` (spec 2026-10-21 M2, file-size cap): the entry a
turn uses, what one listing learned about a server (pages followed, canonical
order, the list's caching hints) and the entry a persisted snapshot stands for.
The pool owns the entries; this module owns their shape.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, NamedTuple
from uuid import UUID

import httpx2
import structlog

from src.core.config import settings
from src.core.constants import MCP_DISCOVERY_MAX_PAGES
from src.infrastructure.mcp.catalogue_snapshot import (
    CacheScope,
    CatalogueSnapshot,
    horizon_seconds,
    revalidation_interval_seconds,
    stored_generation,
)
from src.infrastructure.mcp.utils import (
    extract_app_meta,
    extract_output_schema,
    extract_tool_annotations,
    extract_tool_title,
)

logger = structlog.get_logger(__name__)


@dataclass
class PoolEntry:
    """Tool metadata for a connected user MCP server (no persistent session)."""

    user_id: UUID
    server_id: UUID
    last_used: float
    url: str = ""
    auth: httpx2.Auth | None = None
    extra_headers: dict[str, str] | None = None  # plugin mcp.json fixed headers (ADR-225)
    timeout_seconds: int = 30
    tools: list[dict[str, Any]] = field(default_factory=list)
    active_calls: int = 0  # Reference counter — prevents eviction during active tool calls
    # read_me, fetched at real use on this worker (spec 2026-10-21 §5.5b): the text of
    # the last successful fetch, when it settled, and when the last attempt settled.
    reference_content: str | None = None
    reference_fetched_at: datetime | None = None
    reference_attempted_at: datetime | None = None
    discovered_at: float = field(default_factory=time.monotonic)
    catalogue_fingerprint: str = ""
    configuration_fingerprint: str = ""
    has_reference_tool: bool = False
    server_ttl_ms: int | None = None
    cache_scope: CacheScope | None = None
    server_instructions: str | None = None
    # Reserved before the discovery that produced it, or the hydrated snapshot's.
    generation: int = 0
    # False once past its revalidation age: verified at use (spec 2026-10-21 §5.5).
    catalogue_verified: bool = True
    # Old enough for a background revalidation (never sooner than the setting).
    revalidation_due: bool = False
    # Hydrated from the persisted snapshot rather than discovered by this worker.
    from_snapshot: bool = False


def serves_warm(entry: PoolEntry, configuration: str, stored: int | None) -> bool:
    """The worker's entry answers for this configuration, and the row holds nothing newer."""
    return entry.configuration_fingerprint == configuration and (
        stored is None or entry.generation >= stored
    )


#: How a listing ended: whole, or stopped by one of its guards.
ListingOutcome = Literal["complete", "repeated_cursor", "page_cap", "tool_cap"]


@dataclass(frozen=True)
class DiscoveredCatalogue:
    """What one discovery learned about a server.

    Attributes:
        tools: The normalized declarations, sorted by name (canonical order).
        has_reference_tool: The server exposes the ``read_me`` convention tool
            (never called here: it is read at real use).
        server_ttl_ms: The list's ``ttlMs`` (MCP 2026-07-28), if the server gave one.
        cache_scope: The list's ``cacheScope``, if the server gave one.
        server_instructions: The handshake's ``instructions``, if any.
        outcome: Whether the listing ended whole or on a guard.
    """

    tools: list[dict[str, Any]]
    has_reference_tool: bool = False
    server_ttl_ms: int | None = None
    cache_scope: CacheScope | None = None
    server_instructions: str | None = None
    outcome: ListingOutcome = "complete"


async def list_every_tool(client: Any) -> tuple[list[Any], Any, ListingOutcome]:
    """Follow ``nextCursor`` until the last page, a repeated cursor, the page or tool cap.

    Returns:
        The listed tools (at most ``mcp_max_tools_per_server``), the first page
        (it carries the list's caching hints), and how the listing ended.
    """
    max_tools = settings.mcp_max_tools_per_server
    first = await client.list_tools()
    listed = list(first.tools or [])
    seen: set[str] = set()
    cursor = getattr(first, "next_cursor", None)
    outcome: ListingOutcome = "complete"
    pages = 1
    while cursor and len(listed) < max_tools:
        if cursor in seen:
            outcome = "repeated_cursor"
            break
        if pages >= MCP_DISCOVERY_MAX_PAGES:
            outcome = "page_cap"
            break
        seen.add(cursor)
        page = await client.list_tools(cursor=cursor)
        listed.extend(page.tools or [])
        cursor = getattr(page, "next_cursor", None)
        pages += 1
    if len(listed) > max_tools or (cursor and outcome == "complete"):
        outcome = "tool_cap"
    if outcome != "complete":
        logger.info("user_mcp_listing_truncated", outcome=outcome, pages=pages, tools=len(listed))
    return listed[:max_tools], first, outcome


def normalize_tool(tool: Any) -> dict[str, Any]:
    """One declaration as LIA keeps it."""
    app_resource_uri, app_visibility = extract_app_meta(tool)
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.input_schema or {},
        "output_schema": extract_output_schema(tool),
        "title": extract_tool_title(tool),
        "annotations": extract_tool_annotations(tool),
        "app_resource_uri": app_resource_uri,
        "app_visibility": app_visibility,
    }


def ttl_ms(result: Any) -> int | None:
    value = getattr(result, "ttl_ms", None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def cache_scope(result: Any) -> CacheScope | None:
    value = getattr(result, "cache_scope", None)
    if value == "public":
        return "public"
    if value == "private":
        return "private"
    return None


def entry_from_snapshot(
    snapshot: CatalogueSnapshot,
    *,
    user_id: UUID,
    server_id: UUID,
    url: str,
    auth: httpx2.Auth | None,
    timeout_seconds: int,
    extra_headers: dict[str, str] | None,
    verified: bool,
) -> PoolEntry:
    """The pool entry a persisted snapshot stands for — no I/O.

    The entry keeps the row's CURRENT connection (URL, auth, headers): a call
    made with it runs the same authentication flow as after a discovery, OAuth
    refresh included. Its age is the snapshot's, so the revalidation horizon
    keeps counting from the listing, not from the hydration.
    """
    age = max(0.0, snapshot.age_seconds(datetime.now(UTC)))
    now = time.monotonic()
    return PoolEntry(
        user_id=user_id,
        server_id=server_id,
        last_used=now,
        url=url,
        auth=auth,
        extra_headers=extra_headers,
        timeout_seconds=timeout_seconds,
        tools=[dict(tool) for tool in snapshot.tools],
        discovered_at=now - age,
        catalogue_fingerprint=snapshot.catalogue_fingerprint,
        configuration_fingerprint=snapshot.configuration_fingerprint,
        has_reference_tool=snapshot.has_reference_tool,
        server_ttl_ms=snapshot.server_ttl_ms,
        cache_scope=snapshot.cache_scope,
        server_instructions=snapshot.server_instructions,
        generation=snapshot.generation,
        catalogue_verified=verified,
        from_snapshot=True,
    )


def mark_age(entry: PoolEntry, age: float) -> None:
    """Past the server's own horizon: verify at use; past the interval: revalidate."""
    if age >= horizon_seconds(entry.server_ttl_ms):
        entry.catalogue_verified = False
    entry.revalidation_due = age >= revalidation_interval_seconds(entry.server_ttl_ms)


def touched(
    entry: PoolEntry, auth: httpx2.Auth | None, headers: dict[str, str] | None
) -> PoolEntry:
    """The entry served to a caller, with its current credentials and last use."""
    entry.auth = auth  # tokens may have been refreshed
    entry.extra_headers = headers
    entry.last_used = time.monotonic()
    return entry


def warm_entry(entry: PoolEntry | None, configuration: str, stored: object) -> PoolEntry | None:
    """Under the lock, the entry a discovery just installed for this turn, if any.

    The turn already counted its cache outcome on the way in: this re-check counts
    nothing, it only spares a second discovery of the same server.
    """
    if entry is None or not serves_warm(entry, configuration, stored_generation(stored)):
        return None
    mark_age(entry, time.monotonic() - entry.discovered_at)
    return entry


def refresh_reason(entry: PoolEntry, configuration: str, force_refresh: bool) -> str | None:
    """Why a worker's entry may not serve a caller outside a turn's preparation."""
    if force_refresh:
        return "forced"
    if entry.configuration_fingerprint and entry.configuration_fingerprint != configuration:
        return "configuration"
    if time.monotonic() - entry.discovered_at >= settings.mcp_user_pool_ttl_seconds:
        return "age"
    return None


def frozen_declaration(entry: PoolEntry, tool_name: str) -> dict[str, Any] | None:
    """The declaration the entry holds for a tool (what the call was built from)."""
    return next((tool for tool in entry.tools if tool.get("name") == tool_name), None)


class Connection(NamedTuple):
    """The row's current connection settings, as a turn prepares it."""

    url: str
    auth: httpx2.Auth | None
    timeout_seconds: int
    extra_headers: dict[str, str] | None


__all__ = [
    "Connection",
    "DiscoveredCatalogue",
    "ListingOutcome",
    "PoolEntry",
    "cache_scope",
    "entry_from_snapshot",
    "frozen_declaration",
    "list_every_tool",
    "mark_age",
    "normalize_tool",
    "refresh_reason",
    "serves_warm",
    "touched",
    "ttl_ms",
    "warm_entry",
]
