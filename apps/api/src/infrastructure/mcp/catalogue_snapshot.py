"""The persisted catalogue of a personal MCP server: one versioned shape, one parser.

``user_mcp_servers.discovered_tools_cache`` used to hold a bare list of tools,
with no date, no fingerprint and no word on the configuration that produced it,
so nothing could serve a turn from it: 48 % of production turns discovered
their servers over the network again (spec 2026-10-21 §0ter). It becomes a
versioned envelope (§5.2, ADR-338 amendment for this case only):

- **Routable** only while its configuration fingerprint — URL, credential or
  OAuth grant identity, timeout, headers — matches the row being prepared;
  the snapshot lives on the account's own row, so it is never shared across
  accounts, and a changed credential or grant is a miss (MCP 2026-07-28: a
  ``private`` list « MUST NOT be shared across authorization contexts »).
- **Canonical order**: tools sorted by name, so a reordered listing is the same
  catalogue (MCP asks servers for a deterministic order because clients and
  prompt caches depend on it).
- **Revalidated** after the server's own ``ttlMs`` when it gives one, after
  ``MCP_USER_CATALOGUE_REVALIDATE_AFTER_SECONDS`` otherwise; age never refuses
  a snapshot, it schedules a revalidation.
- **Generation**: a number reserved BEFORE the discovery starts; a publication
  carrying an older one than the stored snapshot is refused, so a slow
  discovery never overwrites a newer one (LibreChat's ticket, the MCP SDK's
  generation bump).
- **Legacy shapes** (a list, an older dict) are read forever by the UI and the
  description generator, and never serve the router.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Final, Literal, cast

from src.core.config import settings
from src.infrastructure.mcp.catalogue_fingerprint import canonical_fingerprint

SNAPSHOT_VERSION: Final = 2
#: The upper bound of ``mcp_reference_content_max_chars``: the stored reference
#: is bounded here, the planner truncates further at the configured value.
REFERENCE_MAX_CHARS: Final = 50_000
#: Same bound for the server's handshake instructions.
INSTRUCTIONS_MAX_CHARS: Final = 50_000
#: SEP-2549 caps any ``ttlMs`` at 24 hours.
SERVER_TTL_MAX_MS: Final = 24 * 60 * 60 * 1000

CacheScope = Literal["public", "private"]


@dataclass(frozen=True)
class CatalogueSnapshot:
    """One discovery of a personal server's catalogue, as persisted and served.

    Attributes:
        discovered_at: When the listing was taken (UTC).
        configuration_fingerprint: The row configuration it was taken under.
        catalogue_fingerprint: The tools' fingerprint (tools only, canonical order).
        tools: The normalized tool declarations, sorted by name.
        generation: Reserved before the discovery started; monotonic.
        has_reference_tool: The server exposes the ``read_me`` convention tool.
        reference_content: ``read_me``'s content, fetched at real use (bounded).
        reference_fetched_at: When that content was fetched (UTC).
        server_ttl_ms: The server's ``ttlMs`` for its list (SEP-2549), if any.
        cache_scope: The server's ``cacheScope`` for its list, if any.
        server_instructions: The handshake's ``instructions`` (bounded).
        version: The envelope version.
    """

    discovered_at: datetime
    configuration_fingerprint: str
    catalogue_fingerprint: str
    tools: tuple[Mapping[str, Any], ...]
    generation: int
    has_reference_tool: bool = False
    reference_content: str | None = None
    reference_fetched_at: datetime | None = None
    server_ttl_ms: int | None = None
    cache_scope: CacheScope | None = None
    server_instructions: str | None = None
    version: Literal[2] = field(default=SNAPSHOT_VERSION)

    def age_seconds(self, now: datetime) -> float:
        """Seconds since the listing was taken."""
        return (now - self.discovered_at).total_seconds()


@dataclass(frozen=True)
class ValidSnapshot:
    """A version-2 envelope that parsed whole."""

    snapshot: CatalogueSnapshot

    @property
    def tools(self) -> tuple[Mapping[str, Any], ...]:
        return self.snapshot.tools


@dataclass(frozen=True)
class LegacySnapshot:
    """A list, or an older dict with ``tools``: readable, never routable."""

    tools: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class InvalidSnapshot:
    """Nothing usable: absent, unknown version or malformed."""

    reason: str
    tools: tuple[Mapping[str, Any], ...] = ()


CatalogueSnapshotRead = ValidSnapshot | LegacySnapshot | InvalidSnapshot


def reserve_generation() -> int:
    """A generation for a discovery about to start: later reservations are larger.

    The host's clock in nanoseconds: every worker of one deployment reads the
    same clock, so a discovery reserved first and published last carries the
    smaller number and is refused.
    """
    return time.time_ns()


def stored_generation(raw: object) -> int | None:
    """The generation a version-2 envelope declares, read without parsing it.

    What a turn compares with the snapshot its worker already holds: only a
    NEWER stored generation is worth parsing (spec 2026-10-21 §5.2, review
    focus 3 — a server at its tool cap is parsed once per worker per snapshot).

    Args:
        raw: The column's value, whatever wrote it.

    Returns:
        The declared generation, or None for any other shape.
    """
    if not isinstance(raw, dict) or raw.get("version") != SNAPSHOT_VERSION:
        return None
    generation = raw.get("generation")
    return generation if isinstance(generation, int) and not isinstance(generation, bool) else None


def catalogue_fingerprint(tools: Sequence[Mapping[str, Any]]) -> str:
    """The fingerprint of a catalogue's tools, whatever order the server listed them in."""
    return canonical_fingerprint({"tools": _canonical(tools)})


def build_snapshot(
    *,
    tools: Sequence[Mapping[str, Any]],
    configuration_fingerprint: str,
    discovered_at: datetime,
    generation: int,
    has_reference_tool: bool = False,
    reference_content: str | None = None,
    reference_fetched_at: datetime | None = None,
    server_ttl_ms: int | None = None,
    cache_scope: CacheScope | None = None,
    server_instructions: str | None = None,
) -> CatalogueSnapshot:
    """Assemble a snapshot: canonical order, tools-only fingerprint, bounded texts.

    Returns:
        The snapshot.
    """
    canonical = _canonical(tools)
    return CatalogueSnapshot(
        discovered_at=discovered_at,
        configuration_fingerprint=configuration_fingerprint,
        catalogue_fingerprint=canonical_fingerprint({"tools": list(canonical)}),
        tools=canonical,
        generation=generation,
        has_reference_tool=has_reference_tool,
        reference_content=_bounded(reference_content, REFERENCE_MAX_CHARS),
        reference_fetched_at=reference_fetched_at,
        server_ttl_ms=server_ttl_ms,
        cache_scope=cache_scope,
        server_instructions=_bounded(server_instructions, INSTRUCTIONS_MAX_CHARS),
    )


def with_reference(
    snapshot: CatalogueSnapshot, content: str | None, fetched_at: datetime
) -> CatalogueSnapshot:
    """The same snapshot carrying a freshly fetched ``read_me`` (bounded)."""
    return replace(
        snapshot,
        reference_content=_bounded(content, REFERENCE_MAX_CHARS),
        reference_fetched_at=fetched_at,
    )


def snapshot_to_jsonb(snapshot: CatalogueSnapshot) -> dict[str, Any]:
    """The envelope to persist — always a NEW plain dict (no in-place JSONB mutation)."""
    return {
        "version": snapshot.version,
        "discovered_at": snapshot.discovered_at.isoformat(),
        "configuration_fingerprint": snapshot.configuration_fingerprint,
        "catalogue_fingerprint": snapshot.catalogue_fingerprint,
        "tools": [dict(tool) for tool in snapshot.tools],
        "generation": snapshot.generation,
        "has_reference_tool": snapshot.has_reference_tool,
        "reference_content": snapshot.reference_content,
        "reference_fetched_at": (
            snapshot.reference_fetched_at.isoformat() if snapshot.reference_fetched_at else None
        ),
        "server_ttl_ms": snapshot.server_ttl_ms,
        "cache_scope": snapshot.cache_scope,
        "server_instructions": snapshot.server_instructions,
    }


def parse_catalogue_snapshot(raw: object) -> CatalogueSnapshotRead:
    """Read the column's value, whatever wrote it.

    Args:
        raw: The JSONB value — a version-2 envelope, a legacy list or dict, or nothing.

    Returns:
        ``ValidSnapshot``, ``LegacySnapshot`` or ``InvalidSnapshot``; never raises.
    """
    if isinstance(raw, list):
        tools = _tool_list(raw)
        return LegacySnapshot(tools=tools) if tools is not None else InvalidSnapshot("tools")
    if not isinstance(raw, dict):
        return InvalidSnapshot(reason="absent")
    if "version" not in raw:
        tools = _tool_list(raw.get("tools"))
        return LegacySnapshot(tools=tools) if tools is not None else InvalidSnapshot("tools")
    if raw.get("version") != SNAPSHOT_VERSION:
        return InvalidSnapshot(reason="version")
    try:
        return ValidSnapshot(snapshot=_snapshot_from(raw))
    except (TypeError, ValueError, KeyError) as exc:
        return InvalidSnapshot(reason=type(exc).__name__)


def snapshot_routes(read: CatalogueSnapshotRead, *, configuration_fingerprint: str) -> bool:
    """Whether a persisted snapshot may prepare a turn for the row as configured now.

    Only a valid, non-empty snapshot taken under the SAME configuration
    fingerprint routes — whatever its ``cache_scope``: the snapshot lives on
    the account's own row, and the fingerprint carries the credential or grant
    identity, so a private list is never served under another authorization
    context.
    """
    return (
        isinstance(read, ValidSnapshot)
        and bool(read.snapshot.tools)
        and read.snapshot.configuration_fingerprint == configuration_fingerprint
    )


def revalidation_horizon_seconds(snapshot: CatalogueSnapshot) -> float:
    """How old the snapshot may grow before a background revalidation (never a refusal)."""
    return horizon_seconds(snapshot.server_ttl_ms)


def revalidation_interval_seconds(server_ttl_ms: int | None) -> float:
    """How old a catalogue may grow before a BACKGROUND revalidation is due.

    Never sooner than ``mcp_user_catalogue_revalidate_after_seconds``: a short
    ``ttlMs`` honoured here would rediscover the server on every turn, holding
    discovery slots a cold server waits for. The server's shorter ``ttlMs`` is
    honoured where it is cheaper — the entry is unverified, so a call checks the
    declaration in its own session (§5.5) — and a longer one spaces the
    revalidations further.
    """
    return max(
        horizon_seconds(server_ttl_ms),
        float(settings.mcp_user_catalogue_revalidate_after_seconds),
    )


def horizon_seconds(server_ttl_ms: int | None) -> float:
    """The server's own ``ttlMs`` (capped at 24 h) when it gave one, else the setting.

    A ``ttlMs`` of zero is the official SDK's default for a server that declared
    nothing (measured on mcp 2.2.0), not a server asking to be checked on every
    turn: read as one, it put a full listing before the first call of every turn.
    """
    if server_ttl_ms is not None and server_ttl_ms > 0:
        return min(server_ttl_ms, SERVER_TTL_MAX_MS) / 1000
    return float(settings.mcp_user_catalogue_revalidate_after_seconds)


def _canonical(tools: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    return tuple(sorted((dict(tool) for tool in tools), key=lambda tool: str(tool.get("name", ""))))


def _bounded(text: str | None, limit: int) -> str | None:
    return text[:limit] if isinstance(text, str) else None


def _tool_list(value: object) -> tuple[Mapping[str, Any], ...] | None:
    if not isinstance(value, list) or not all(isinstance(tool, dict) for tool in value):
        return None
    if len(value) > settings.mcp_max_tools_per_server:
        return None
    return tuple(cast(list[dict[str, Any]], value))


def _instant(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("instant")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("naive instant")
    return parsed.astimezone(UTC)


def _optional_text(value: object) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError("text")


def _snapshot_from(raw: Mapping[str, Any]) -> CatalogueSnapshot:
    tools = _tool_list(raw["tools"])
    if tools is None:
        raise ValueError("tools")
    scope = raw.get("cache_scope")
    if scope not in (None, "public", "private"):
        raise ValueError("cache_scope")
    ttl = raw.get("server_ttl_ms")
    if ttl is not None and (not isinstance(ttl, int) or isinstance(ttl, bool)):
        raise ValueError("server_ttl_ms")
    generation = raw["generation"]
    if not isinstance(generation, int) or isinstance(generation, bool):
        raise ValueError("generation")
    fetched = raw.get("reference_fetched_at")
    return CatalogueSnapshot(
        discovered_at=_instant(raw["discovered_at"]),
        configuration_fingerprint=str(raw["configuration_fingerprint"]),
        catalogue_fingerprint=str(raw["catalogue_fingerprint"]),
        tools=tools,
        generation=generation,
        has_reference_tool=bool(raw.get("has_reference_tool", False)),
        reference_content=_optional_text(raw.get("reference_content")),
        reference_fetched_at=_instant(fetched) if fetched is not None else None,
        server_ttl_ms=ttl,
        cache_scope=cast(CacheScope | None, scope),
        server_instructions=_optional_text(raw.get("server_instructions")),
    )


__all__ = [
    "REFERENCE_MAX_CHARS",
    "SNAPSHOT_VERSION",
    "CacheScope",
    "CatalogueSnapshot",
    "CatalogueSnapshotRead",
    "InvalidSnapshot",
    "LegacySnapshot",
    "ValidSnapshot",
    "build_snapshot",
    "catalogue_fingerprint",
    "horizon_seconds",
    "parse_catalogue_snapshot",
    "reserve_generation",
    "revalidation_horizon_seconds",
    "revalidation_interval_seconds",
    "snapshot_routes",
    "snapshot_to_jsonb",
    "stored_generation",
    "with_reference",
]
