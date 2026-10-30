"""Writes of a personal MCP server's catalogue snapshot (spec 2026-10-21 §5.2).

Two writers, one shape (``infrastructure/mcp/catalogue_snapshot``):

- **The manual test** (``test_connection``) builds the whole probe update here —
  status, the version-2 snapshot, the generated routing description and the
  tool vectors — and writes it through its own guarded update. It is the
  person's forced refresh, so it always writes what it just discovered.
- **The conditional publication** (``publish_catalogue_if_current``), for every
  writer that does not hold the row (a turn's cold discovery, a background
  revalidation, a ``read_me`` fetched at real use): in a short session of its
  own it locks the row, recomputes its connection fingerprint, and writes a NEW
  envelope only if the row is still active and enabled, still configured as
  the snapshot was taken, and holds no NEWER generation. Anything else is
  refused and counted by reason — a slow discovery never overwrites a newer
  one, and an edited URL or credential never receives the old catalogue.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

import structlog
from sqlalchemy import select

from src.core.time_utils import now_utc
from src.domains.user_mcp.connection_embeddings import build_connection_embeddings
from src.domains.user_mcp.models import UserMCPAuthType, UserMCPServer, UserMCPServerStatus
from src.infrastructure.mcp.catalogue_snapshot import (
    CatalogueSnapshot,
    ValidSnapshot,
    build_snapshot,
    parse_catalogue_snapshot,
    snapshot_to_jsonb,
    with_reference,
)
from src.infrastructure.observability.metrics_mcp import mcp_user_catalogue_publications_total

if TYPE_CHECKING:
    from src.domains.user_mcp.service import UserMCPServerService
    from src.infrastructure.mcp.user_pool import PoolEntry

logger = structlog.get_logger(__name__)

PublicationOutcome = Literal[
    "published", "configuration_changed", "inactive", "missing", "superseded"
]


def snapshot_from_entry(
    entry: PoolEntry, *, generation: int, discovered_at: datetime
) -> CatalogueSnapshot:
    """The snapshot of what a pool entry just discovered.

    Args:
        entry: The pool entry the discovery produced.
        generation: Reserved before the discovery started.
        discovered_at: When the listing was taken (UTC).

    Returns:
        The snapshot to persist.
    """
    return build_snapshot(
        tools=entry.tools,
        configuration_fingerprint=entry.configuration_fingerprint,
        discovered_at=discovered_at,
        generation=generation,
        has_reference_tool=entry.has_reference_tool,
        server_ttl_ms=entry.server_ttl_ms,
        cache_scope=entry.cache_scope,
        server_instructions=entry.server_instructions,
    )


async def probe_update_data(
    service: UserMCPServerService,
    server: UserMCPServer,
    entry: PoolEntry,
    *,
    user_id: UUID,
    generation: int,
) -> dict[str, Any]:
    """The manual test's update: status, snapshot, routing description and tool vectors.

    Args:
        service: The server service (its description generator).
        server: The tested row.
        entry: What the forced discovery produced.
        user_id: The account (spend attribution).
        generation: Reserved before the discovery started.

    Returns:
        The column values to write in one update.
    """
    update_data: dict[str, Any] = {
        "discovered_tools_cache": snapshot_to_jsonb(
            snapshot_from_entry(entry, generation=generation, discovered_at=now_utc())
        ),
        "status": UserMCPServerStatus.ACTIVE.value,
        "last_connected_at": now_utc(),
        "last_error": None,
    }
    # Auto-generate domain_description if not user-provided
    if not server.domain_description:
        update_data["domain_description"] = await service._llm_generate_description(
            tool_list=entry.tools,
            server_name=server.name,
            account_scoped=server.auth_type != UserMCPAuthType.NONE.value,
            user_id=server.user_id,
        )
    # Compute E5 embeddings for semantic scoring (evolution F2.1)
    try:
        from src.domains.agents.services.tool_embeddings_envelope import wrap_server_cache
        from src.domains.agents.services.tool_selector import compute_tool_embeddings

        tool_embeddings = await build_connection_embeddings(
            user_id, server.name, entry.tools, compute_tool_embeddings
        )
        if tool_embeddings:
            # The model that wrote the vectors travels with them: a cache of
            # another width scored every tool 0 in silence.
            update_data["tool_embeddings_cache"] = wrap_server_cache(
                tool_embeddings, tool_metadata=entry.tools, server_name=server.name[:100]
            )
    except Exception:
        logger.warning(
            "user_mcp_embedding_computation_failed", server_id=str(server.id), exc_info=True
        )
    return update_data


async def publish_catalogue_if_current(
    *,
    user_id: UUID,
    server_id: UUID,
    snapshot: CatalogueSnapshot,
    tool_embeddings: Mapping[str, Any] | None,
) -> PublicationOutcome:
    """Write a snapshot only if the row is still the one it was taken from.

    Args:
        user_id: The account owning the row.
        server_id: The server.
        snapshot: What the discovery produced.
        tool_embeddings: A new vector envelope to write with it, or None.

    Returns:
        ``published``, or why the snapshot was refused.
    """
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        row = (
            await db.execute(
                select(UserMCPServer)
                .where(UserMCPServer.id == server_id, UserMCPServer.user_id == user_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        outcome: PublicationOutcome = (
            "missing" if row is None else _publish_into(row, snapshot, tool_embeddings)
        )
    mcp_user_catalogue_publications_total.labels(outcome=outcome).inc()
    if outcome != "published":
        logger.info(
            "user_mcp_catalogue_publication_refused", server_id=str(server_id), outcome=outcome
        )
    return outcome


def _publish_into(
    row: UserMCPServer, snapshot: CatalogueSnapshot, tool_embeddings: Mapping[str, Any] | None
) -> PublicationOutcome:
    """Write into a LOCKED row, or say why it cannot receive the snapshot."""
    from src.infrastructure.mcp.auth import build_auth_for_server
    from src.infrastructure.mcp.catalogue_fingerprint import connection_fingerprint

    if not row.is_enabled or row.status != UserMCPServerStatus.ACTIVE.value:
        return "inactive"
    stored = parse_catalogue_snapshot(row.discovered_tools_cache)
    if isinstance(stored, ValidSnapshot) and stored.snapshot.generation > snapshot.generation:
        return "superseded"
    current = connection_fingerprint(
        row.url, build_auth_for_server(row), row.timeout_seconds, row.extra_headers
    )
    if current != snapshot.configuration_fingerprint:
        return "configuration_changed"
    if isinstance(stored, ValidSnapshot):
        snapshot = _keep_reference(snapshot, stored.snapshot)
    # NEW dicts: an in-place JSONB mutation is skipped by SQLAlchemy.
    row.discovered_tools_cache = snapshot_to_jsonb(snapshot)
    if tool_embeddings is not None:
        row.tool_embeddings_cache = dict(tool_embeddings)
    return "published"


def _keep_reference(snapshot: CatalogueSnapshot, stored: CatalogueSnapshot) -> CatalogueSnapshot:
    """A rediscovered catalogue keeps the stored ``read_me`` — only a catalogue change clears it.

    Discovery never reads ``read_me`` (spec 2026-10-21 §5.5b): a revalidation
    of an unchanged catalogue would otherwise erase what a real use fetched.
    """
    if (
        snapshot.reference_fetched_at is not None
        or stored.reference_fetched_at is None
        or stored.catalogue_fingerprint != snapshot.catalogue_fingerprint
    ):
        return snapshot
    return with_reference(snapshot, stored.reference_content, stored.reference_fetched_at)


__all__ = [
    "PublicationOutcome",
    "probe_update_data",
    "publish_catalogue_if_current",
    "snapshot_from_entry",
]
