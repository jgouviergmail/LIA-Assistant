"""A personal MCP server's guidance, read at real use (spec 2026-10-21 §5.5b, A15).

Two texts tell the pipeline planner how to call a server's tools: the
``instructions`` its handshake carries (MCP's own channel, captured at
discovery at no extra cost) and the ``read_me`` convention tool some servers
expose. Discovery used to CALL ``read_me`` for every server offering it; the
reference is now fetched only when the planner prepares a turn whose
router-selected domains include that server — found through the EXACT domain
the registration allocated, never by comparing a raw name with a slug (E9).

- A stored reference (this worker's pool entry, or the persisted snapshot when
  it describes this very catalogue) is served as is.
- None yet: fetched once, inline, bounded by
  ``min(mcp_user_discovery_timeout_seconds, server.timeout_seconds)`` under a
  claim the workers share.
- Older than ``mcp_user_catalogue_revalidate_after_seconds``: served, and
  refreshed in the background.
- A failed fetch plans without reference, as when the server has no
  ``read_me``; it is remembered, so a later turn never waits on it again — the
  next attempt is a background one, once the same age has passed.

The fetched text is written into the snapshot through the conditional
publication (same generation: a newer discovery refuses it). The ReAct loop is
offered ``read_me`` as a ReAct-only tool instead (``user_context``, E10);
iterative servers keep theirs inside their sub-agent and have no source here.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.context import user_mcp_tools_ctx
from src.domains.user_mcp.catalogue_publication import publish_catalogue_if_current
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.locks.redis_claim import release_claim, try_claim
from src.infrastructure.mcp.catalogue_snapshot import (
    CatalogueSnapshot,
    ValidSnapshot,
    parse_catalogue_snapshot,
    with_reference,
)
from src.infrastructure.mcp.user_pool import PoolEntry, get_user_mcp_pool
from src.infrastructure.observability.metrics_mcp import mcp_user_reference_fetches_total

if TYPE_CHECKING:
    from src.domains.user_mcp.models import UserMCPServer

logger = structlog.get_logger(__name__)

#: How a fetch ended; ``busy`` — another worker holds the claim.
ReferenceOutcome = Literal["fetched", "empty", "failed", "timed_out", "busy"]

#: The claim outlives the bounded fetch it guards, its publication included.
_CLAIM_TTL_FACTOR = 2


@dataclass(frozen=True)
class ReferenceSource:
    """What the pipeline planner may read about one standard personal server.

    Attributes:
        user_id: The account owning the server.
        server_id: The server.
        domain: The exact domain slug the registration allocated to it.
        timeout_seconds: The server's own tool timeout.
        entry: The pool entry — this worker's copy of the fetched reference.
        snapshot: The persisted snapshot, only when it describes this very
            catalogue and configuration; a fetched reference is published into it.
    """

    user_id: UUID
    server_id: UUID
    domain: str
    timeout_seconds: int
    entry: PoolEntry
    snapshot: CatalogueSnapshot | None


def reference_source(
    server: UserMCPServer, entry: PoolEntry, *, user_id: UUID, domain: str
) -> ReferenceSource | None:
    """The source of a standard server registered for this turn.

    Args:
        server: The server row read for this turn.
        entry: What the pool holds for it.
        user_id: The account.
        domain: Its exact domain slug.

    Returns:
        The source, or None when the server offers neither ``read_me`` nor instructions.
    """
    if not (entry.has_reference_tool or entry.server_instructions):
        return None
    read = parse_catalogue_snapshot(server.discovered_tools_cache)
    snapshot = (
        read.snapshot
        if isinstance(read, ValidSnapshot) and _describes(read.snapshot, entry)
        else None
    )
    return ReferenceSource(
        user_id=user_id,
        server_id=server.id,
        domain=domain,
        timeout_seconds=server.timeout_seconds,
        entry=entry,
        snapshot=snapshot,
    )


def _describes(snapshot: CatalogueSnapshot, entry: PoolEntry) -> bool:
    """A stored reference documents THIS catalogue: a catalogue change clears it."""
    return (
        snapshot.catalogue_fingerprint == entry.catalogue_fingerprint
        and snapshot.configuration_fingerprint == entry.configuration_fingerprint
    )


def reference_claim_key(user_id: UUID, server_id: UUID) -> str:
    """The claim one worker holds while it fetches a server's ``read_me``."""
    return f"mcp:catalogue:reference:{user_id}:{server_id}"


async def collect_user_references(
    selected_domains: Sequence[str], *, now: datetime
) -> dict[str, str]:
    """The guidance of every standard personal server whose domain was selected.

    Args:
        selected_domains: The router-selected domain slugs.
        now: The turn's instant (UTC).

    Returns:
        Server name → its instructions then its reference; servers with neither
        are absent. Never raises: a failed fetch yields no reference.
    """
    ctx = user_mcp_tools_ctx.get()
    if ctx is None:
        return {}
    selected = set(selected_domains)
    chosen = [
        (name, source)
        for name, source in ctx.server_reference_sources.items()
        if source.domain in selected
    ]
    texts = await asyncio.gather(*(_guidance(source, now) for _name, source in chosen))
    return {name: text for (name, _source), text in zip(chosen, texts, strict=True) if text}


async def _guidance(source: ReferenceSource, now: datetime) -> str:
    reference = await _reference(source, now) if source.entry.has_reference_tool else None
    return "\n\n".join(part for part in (source.entry.server_instructions, reference) if part)


async def _reference(source: ReferenceSource, now: datetime) -> str | None:
    """Serve what is stored; fetch inline only when nothing was ever tried."""
    content, fetched_at = _stored(source)
    tried = max(
        (instant for instant in (fetched_at, source.entry.reference_attempted_at) if instant),
        default=None,
    )
    if tried is None:
        return await _fetch(source, now)
    if (now - tried).total_seconds() >= settings.mcp_user_catalogue_revalidate_after_seconds:
        # Marked when scheduled: the turns that follow while it runs schedule none.
        source.entry.reference_attempted_at = now
        safe_fire_and_forget(_fetch(source, now), name="mcp_user_reference_refresh")
    return content


def _stored(source: ReferenceSource) -> tuple[str | None, datetime | None]:
    """The most recent successful fetch: this worker's, or the persisted one."""
    held: list[tuple[str | None, datetime]] = []
    if source.entry.reference_fetched_at is not None:
        held.append((source.entry.reference_content, source.entry.reference_fetched_at))
    snapshot = source.snapshot
    if snapshot is not None and snapshot.reference_fetched_at is not None:
        held.append((snapshot.reference_content, snapshot.reference_fetched_at))
    if not held:
        return None, None
    return max(held, key=lambda pair: pair[1])


async def _fetch(source: ReferenceSource, now: datetime) -> str | None:
    """Fetch once under the shared claim, keep it on the worker, publish it. Never raises."""
    bound = min(settings.mcp_user_discovery_timeout_seconds, source.timeout_seconds)
    key = reference_claim_key(source.user_id, source.server_id)
    token = uuid.uuid4().hex
    try:
        redis = await get_redis_cache()
        if not await try_claim(redis, key, token, ttl_seconds=bound * _CLAIM_TTL_FACTOR):
            _settle(source, "busy", None, now)
            return None
    except Exception:
        # The claim only spares a duplicate fetch: a cache outage never costs
        # the turn its reference.
        redis = None
    try:
        outcome, content = await _read(source, bound)
        _settle(source, outcome, content, now)
        if outcome in ("fetched", "empty") and source.snapshot is not None:
            await _publish(source, source.snapshot, content, now)
        return content
    finally:
        if redis is not None:
            await release_claim(redis, key, token)


async def _read(source: ReferenceSource, bound: int) -> tuple[ReferenceOutcome, str | None]:
    pool = get_user_mcp_pool()
    if pool is None:
        return "failed", None
    try:
        text = await pool.fetch_reference(source.user_id, source.server_id, bound)
    except TimeoutError:
        return "timed_out", None
    except Exception as exc:
        logger.info(
            "user_mcp_reference_fetch_failed",
            server_id=str(source.server_id),
            error_type=type(exc).__name__,
        )
        return "failed", None
    return ("fetched", text) if text else ("empty", None)


def _settle(
    source: ReferenceSource, outcome: ReferenceOutcome, content: str | None, now: datetime
) -> None:
    """Record the attempt on the worker; a failure never erases a stored reference."""
    mcp_user_reference_fetches_total.labels(outcome=outcome).inc()
    entry = source.entry
    if outcome == "busy":
        return
    entry.reference_attempted_at = now
    if outcome in ("fetched", "empty"):
        entry.reference_content, entry.reference_fetched_at = content, now
    logger.info(
        "user_mcp_reference_fetched",
        server_id=str(source.server_id),
        outcome=outcome,
        content_length=len(content or ""),
    )


async def _publish(
    source: ReferenceSource, snapshot: CatalogueSnapshot, content: str | None, now: datetime
) -> None:
    # The worker already holds the text; a refused or failed write only costs
    # the other workers a fetch of their own.
    try:
        await publish_catalogue_if_current(
            user_id=source.user_id,
            server_id=source.server_id,
            snapshot=with_reference(snapshot, content, now),
            tool_embeddings=None,
        )
    except Exception:
        logger.warning(
            "user_mcp_reference_publication_failed", server_id=str(source.server_id), exc_info=True
        )


__all__ = [
    "ReferenceSource",
    "collect_user_references",
    "reference_claim_key",
    "reference_source",
]
