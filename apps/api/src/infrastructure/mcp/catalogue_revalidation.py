"""Revalidate an aged personal MCP catalogue in the background (spec 2026-10-21 §5.4).

A turn serves a persisted catalogue whatever its age (ADR-338 amendment, Q1);
age schedules this revalidation and never refuses. It runs off the turn:

- **One worker at a time** per server: a claim on
  ``mcp:catalogue:revalidate:{user}:{server}`` with an owner token, renewed while
  the revalidation runs (the wait for a discovery slot and the vectors may outlast
  its TTL) and released by compare-and-delete; a claim lost to a successor stops
  this run (``claim_lost``). Without the cache it does not run (the snapshot keeps
  serving), rather than let every worker discover at once.
- **A paused server is left alone** until its pause ends; a failure feeds the
  pause, a success clears it (the pool's discovery does both).
- **Discovery with the dedicated timeout**, ``list_tools`` only — never
  ``read_me`` (A15) —, replacing this worker's pool entry; the other workers
  take the newer snapshot at their next turn.
- **Conditional publication** (the one writer): an edited row or a newer
  generation refuses it; the stored reference survives an unchanged catalogue.
- **Vectors** only when the catalogue changed: the missing ones, under the
  account's spending ceilings, attributed to the account.

Silent: no notice, no effect on any turn. Every outcome is counted.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Literal
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.time_utils import now_utc
from src.domains.user_mcp.catalogue_publication import (
    publish_catalogue_if_current,
    snapshot_from_entry,
)
from src.domains.user_mcp.connection_embeddings import embedding_attribution
from src.domains.user_mcp.models import UserMCPServerStatus
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.locks.redis_claim import ClaimLost, held_claim, try_claim
from src.infrastructure.mcp.auth import build_auth_for_server
from src.infrastructure.mcp.catalogue_snapshot import ValidSnapshot, parse_catalogue_snapshot
from src.infrastructure.mcp.server_vectors import usable_tool_embeddings
from src.infrastructure.mcp.user_pool import PoolEntry, get_user_mcp_pool
from src.infrastructure.observability.metrics_mcp import mcp_user_catalogue_revalidations_total

if TYPE_CHECKING:
    from src.domains.user_mcp.models import UserMCPServer

logger = structlog.get_logger(__name__)

RevalidationOutcome = Literal[
    "published",
    "configuration_changed",
    "inactive",
    "missing",
    "superseded",
    "busy",
    "claim_unavailable",
    "claim_lost",
    "paused",
    "failed",
    "timed_out",
]

#: The claim's crash bound: the bounded discovery plus this much. It is renewed while the
#: revalidation runs — the wait for a discovery slot and the vectors may outlast it.
_CLAIM_MARGIN_SECONDS = 30


def revalidation_claim_key(user_id: UUID, server_id: UUID) -> str:
    """The claim one worker holds while it revalidates a server's catalogue."""
    return f"mcp:catalogue:revalidate:{user_id}:{server_id}"


def schedule_catalogue_revalidation(user_id: UUID, server_id: UUID) -> None:
    """Revalidate in the background, owned by the background set (shutdown drain)."""
    safe_fire_and_forget(
        revalidate_catalogue(user_id, server_id), name="mcp_user_catalogue_revalidation"
    )


async def revalidate_catalogue(user_id: UUID, server_id: UUID) -> RevalidationOutcome:
    """Rediscover a server's catalogue and publish it if the row still matches.

    Args:
        user_id: The account owning the server.
        server_id: The server.

    Returns:
        What happened, counted in ``mcp_user_catalogue_revalidations_total``.
        Never raises.
    """
    key = revalidation_claim_key(user_id, server_id)
    token = uuid.uuid4().hex
    ttl = settings.mcp_user_discovery_timeout_seconds + _CLAIM_MARGIN_SECONDS
    try:
        redis = await get_redis_cache()
        claimed = await try_claim(redis, key, token, ttl_seconds=ttl)
    except Exception as exc:
        logger.info("user_mcp_revalidation_claim_unavailable", error_type=type(exc).__name__)
        return _counted("claim_unavailable")
    if not claimed:
        return _counted("busy")
    try:
        # Renewed while it runs, released by its token: a second worker never
        # revalidates (and embeds) beside a slow one.
        async with held_claim(redis, key, token, ttl_seconds=ttl):
            outcome = await _revalidate(user_id, server_id)
    except ClaimLost as lost:
        logger.info(
            "user_mcp_revalidation_claim_lost", server_id=str(server_id), reason=lost.reason
        )
        outcome = "claim_lost"
    except Exception as exc:
        logger.warning(
            "user_mcp_revalidation_failed",
            server_id=str(server_id),
            error_type=type(exc).__name__,
        )
        outcome = "failed"
    return _counted(outcome)


def _counted(outcome: RevalidationOutcome) -> RevalidationOutcome:
    mcp_user_catalogue_revalidations_total.labels(outcome=outcome).inc()
    return outcome


async def _revalidate(user_id: UUID, server_id: UUID) -> RevalidationOutcome:
    server = await _load(user_id, server_id)
    if server is None:
        return "missing"
    if not server.is_enabled or server.status != UserMCPServerStatus.ACTIVE.value:
        return "inactive"
    pool = get_user_mcp_pool()
    if pool is None:
        return "failed"
    if await pool.pause_remaining(user_id, server_id) > 0:
        return "paused"
    try:
        entry = await pool.get_or_connect(
            user_id=user_id,
            server_id=server_id,
            url=server.url,
            auth=build_auth_for_server(server),
            timeout_seconds=server.timeout_seconds,
            extra_headers=server.extra_headers,
            force_refresh=True,
        )
    except TimeoutError:
        return "timed_out"
    outcome = await publish_catalogue_if_current(
        user_id=user_id,
        server_id=server_id,
        snapshot=snapshot_from_entry(entry, generation=entry.generation, discovered_at=now_utc()),
        tool_embeddings=None,
    )
    if outcome == "published" and _catalogue_changed(server, entry):
        with embedding_attribution(user_id, f"mcp-revalidation:{user_id}"):
            await usable_tool_embeddings(server, entry.tools)
    return outcome


async def _load(user_id: UUID, server_id: UUID) -> UserMCPServer | None:
    """The row, in a short session closed before any network (ADR-304)."""
    from src.domains.user_mcp.repository import UserMCPServerRepository
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        server = await UserMCPServerRepository(db).get_by_id(server_id)
    return server if server is not None and server.user_id == user_id else None


def _catalogue_changed(server: UserMCPServer, entry: PoolEntry) -> bool:
    stored = parse_catalogue_snapshot(server.discovered_tools_cache)
    return not (
        isinstance(stored, ValidSnapshot)
        and stored.snapshot.catalogue_fingerprint == entry.catalogue_fingerprint
    )


__all__ = [
    "RevalidationOutcome",
    "revalidate_catalogue",
    "revalidation_claim_key",
    "schedule_catalogue_revalidation",
]
