"""Prepare a turn's personal MCP servers in parallel, under one ceiling (spec 2026-10-21 §5.3).

Servers used to be prepared one after the other, each discovered over the
network whenever this worker held nothing for it: the turn waited for the sum
(measured up to 16.4 s of discovery and vectors on one turn). Now:

- **One child per server**, started through ``safe_fire_and_forget`` (strong
  ownership, shutdown drain). A child serves the worker's entry or hydrates the
  persisted catalogue with no network (``get_or_connect`` decides, from the
  row's snapshot); only a server with neither discovers, holding one of the
  process's discovery slots, under the dedicated timeout, and publishes what it
  found for the next turns and workers. Then the server's vectors.
- **An aged catalogue is served** (Q1); past the revalidation interval it is
  revalidated in the background, never more often than the setting.
- **The parent waits up to the ceiling.** A child still discovering is left out
  of the turn (``deferred``, Q2 (a)) and keeps running: it publishes for the
  next turn. A server still discovering after the notice delay is reported
  ``slow``.
- **Isolation.** A child never raises and never touches the request
  ``ContextVar``: the parent assembles every server in the input order and
  installs the context once. Cancelling the turn stops the WAIT, never a child.
  No database session is shared, none stays open across the network.

``on_event`` receives every phase (``queued`` for all, ``discovering`` only
for a server that went to the network); what reaches a person is decided by its
reader (notices, M4).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.time_utils import now_utc
from src.domains.user_mcp.catalogue_publication import (
    publish_catalogue_if_current,
    snapshot_from_entry,
)
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.mcp.catalogue_revalidation import schedule_catalogue_revalidation
from src.infrastructure.mcp.rate_limit import MCPServerPausedError
from src.infrastructure.mcp.server_vectors import usable_tool_embeddings
from src.infrastructure.mcp.user_pool import PoolEntry, UserMCPClientPool
from src.infrastructure.observability.metrics_mcp import mcp_user_server_preparation_seconds

if TYPE_CHECKING:
    import httpx2

    from src.domains.user_mcp.models import UserMCPServer

logger = structlog.get_logger(__name__)

PreparationPhase = Literal[
    "queued", "discovering", "embeddings", "ready", "failed", "timed_out", "slow", "deferred"
]
PreparationOutcome = Literal["ready", "paused", "failed", "timed_out", "deferred"]
#: ``catalogue`` — the worker's entry or the persisted snapshot, no network.
PreparationSource = Literal["catalogue", "network"]


@dataclass(frozen=True)
class PreparationEvent:
    """One step of one server's preparation, for whoever reports progress."""

    server_id: UUID
    server_name: str
    phase: PreparationPhase
    elapsed_s: float


@dataclass(frozen=True)
class ServerPreparation:
    """What one server brings to the turn.

    Attributes:
        server_id: The server.
        outcome: ``ready`` — usable; ``deferred`` — still discovering at the ceiling.
        source: Where its catalogue came from, when known.
        entry: The pool entry, when ``ready``.
        embeddings: Its tool vectors, by raw tool name.
        duration_s: How long it took (up to the ceiling when deferred).
        error: What stopped it, for the caller's report.
    """

    server_id: UUID
    outcome: PreparationOutcome
    source: PreparationSource | None
    entry: PoolEntry | None
    embeddings: Mapping[str, Any] = field(default_factory=dict)
    duration_s: float = 0.0
    error: BaseException | None = None


EventSink = Callable[[PreparationEvent], None]
AuthFactory = Callable[["UserMCPServer"], "httpx2.Auth"]


def preparation_ceiling_seconds() -> float:
    """The longest a turn waits for its personal servers."""
    return float(settings.mcp_user_preparation_ceiling_seconds)


async def prepare_user_servers(
    user_id: UUID,
    servers: Sequence[UserMCPServer],
    pool: UserMCPClientPool,
    *,
    on_event: EventSink | None,
    ceiling_s: float,
    auth_for: AuthFactory,
) -> list[ServerPreparation]:
    """Prepare every server at once; wait for them up to the ceiling.

    Args:
        user_id: The account.
        servers: Its enabled and active servers, read in a session already closed.
        pool: The worker's pool.
        on_event: Receives every phase of every server, or None.
        ceiling_s: The longest the turn waits.
        auth_for: Builds the auth of a row (the caller's, so its seam stays one).

    Returns:
        One result per server, in the input order.
    """
    if not servers:
        return []
    started = time.monotonic()
    networked: set[UUID] = set()

    def emit(server: UserMCPServer, phase: PreparationPhase) -> None:
        if on_event is None:
            return
        try:
            on_event(PreparationEvent(server.id, server.name, phase, time.monotonic() - started))
        except Exception as exc:
            # Progress is a side channel: its reader failing never costs a server.
            logger.debug("user_mcp_preparation_event_dropped", error_type=type(exc).__name__)

    children = [
        safe_fire_and_forget(
            _prepare_one(user_id, server, pool, emit=emit, networked=networked, auth_for=auth_for),
            name="mcp_user_server_preparation",
        )
        for server in servers
    ]
    slow_after = min(float(settings.mcp_user_slow_preparation_notice_seconds), ceiling_s)
    _done, pending = await asyncio.wait(children, timeout=slow_after)
    # Every server still preparing is told slow, wherever it waits — the network, a
    # discovery slot, another discovery's lock: one told nothing was then deferred at
    # the ceiling with no notice, its tools silently gone (fresh review I4, Q2 (a)).
    for server in _still_preparing(servers, children, pending):
        emit(server, "slow")
    remaining = ceiling_s - (time.monotonic() - started)
    if pending and remaining > 0:
        _done, pending = await asyncio.wait(pending, timeout=remaining)
    for server in _still_preparing(servers, children, pending):
        emit(server, "deferred")
    return [
        _deferred(server, started) if child in pending else child.result()
        for server, child in zip(servers, children, strict=True)
    ]


def _still_preparing(
    servers: Sequence[UserMCPServer],
    children: Sequence[asyncio.Task[ServerPreparation]],
    pending: set[asyncio.Task[ServerPreparation]],
) -> list[UserMCPServer]:
    return [server for server, child in zip(servers, children, strict=True) if child in pending]


def _deferred(server: UserMCPServer, started: float) -> ServerPreparation:
    return ServerPreparation(
        server_id=server.id,
        outcome="deferred",
        source="network",
        entry=None,
        duration_s=time.monotonic() - started,
    )


async def _prepare_one(
    user_id: UUID,
    server: UserMCPServer,
    pool: UserMCPClientPool,
    *,
    emit: Callable[[UserMCPServer, PreparationPhase], None],
    networked: set[UUID],
    auth_for: AuthFactory,
) -> ServerPreparation:
    """One server, from memory, the persisted catalogue or the network. Never raises."""
    started = time.monotonic()

    def on_discovery() -> None:
        networked.add(server.id)
        emit(server, "discovering")

    emit(server, "queued")
    try:
        entry = await pool.get_or_connect(
            user_id=user_id,
            server_id=server.id,
            url=server.url,
            auth=auth_for(server),
            timeout_seconds=server.timeout_seconds,
            extra_headers=server.extra_headers,
            stored_catalogue=server.discovered_tools_cache,
            on_discovery=on_discovery,
        )
        if server.id in networked:
            await _publish(user_id, server, entry)
        if entry.revalidation_due is True:
            schedule_catalogue_revalidation(user_id, server.id)
        emit(server, "embeddings")
        embeddings = await usable_tool_embeddings(server, entry.tools)
    except MCPServerPausedError as paused:
        # A server told « slow » meanwhile is told it was not prepared (Q2 (a)): its
        # notice must not outlive the turn's preparation unexplained.
        emit(server, "failed")
        return _settled(server, "paused", networked, started, error=paused)
    except TimeoutError as timeout:
        emit(server, "timed_out")
        return _settled(server, "timed_out", networked, started, error=timeout)
    except Exception as exc:
        emit(server, "failed")
        return _settled(server, "failed", networked, started, error=exc)
    emit(server, "ready")
    return _settled(server, "ready", networked, started, entry=entry, embeddings=embeddings)


def _settled(
    server: UserMCPServer,
    outcome: PreparationOutcome,
    networked: set[UUID],
    started: float,
    *,
    entry: PoolEntry | None = None,
    embeddings: Mapping[str, Any] | None = None,
    error: BaseException | None = None,
) -> ServerPreparation:
    source: PreparationSource = "network" if server.id in networked else "catalogue"
    duration = time.monotonic() - started
    mcp_user_server_preparation_seconds.labels(source=source, outcome=outcome).observe(duration)
    return ServerPreparation(
        server_id=server.id,
        outcome=outcome,
        source=source,
        entry=entry,
        embeddings=embeddings or {},
        duration_s=duration,
        error=error,
    )


async def _publish(user_id: UUID, server: UserMCPServer, entry: PoolEntry) -> None:
    """Publish what the network said, for the next turns and workers (conditional write)."""
    try:
        await publish_catalogue_if_current(
            user_id=user_id,
            server_id=server.id,
            snapshot=snapshot_from_entry(
                entry, generation=entry.generation, discovered_at=now_utc()
            ),
            tool_embeddings=None,
        )
    except Exception as exc:
        # The turn already holds the catalogue; only the next ones lose the shortcut.
        logger.warning(
            "user_mcp_catalogue_publication_failed",
            server_id=str(server.id),
            error_type=type(exc).__name__,
        )


__all__ = [
    "PreparationEvent",
    "PreparationOutcome",
    "PreparationPhase",
    "ServerPreparation",
    "preparation_ceiling_seconds",
    "prepare_user_servers",
]
