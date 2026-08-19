"""Peers cross-user READ tools (Lot 5 — spec A1, §12.4).

Two read-only tools over the domains a CONNECTED peer chose to share:

- ``get_peer_availability_tool`` — the peer's next-48h calendar as busy slots
  (level ``availability``) or slots + event titles (level ``details``).
- ``get_peer_tasks_tool`` — the peer's pending task titles (level ``titles``).

Non-negotiables, enforced here and tested:
- The share is re-checked AT EXECUTION TIME against the database (never
  cached — a revoked share wins over any in-flight conversation).
- Every read writes one immutable ``peer_access_log`` row the data OWNER can
  consult (transparency, spec §12.4).
- Results are tagged as third-party provenance: shared DATA, never
  instructions (ADR-167/170 doctrine).
- The container read is the one the OWNER configured (their default calendar /
  task list), never a hardcoded ``primary`` — reading someone else's agenda
  from the wrong calendar answers "free" about a busy person.
- What the response model reads is ``message``; ``structured_data`` feeds only
  Jinja inter-step references. Rendering lives in ``agents/peer/summaries.py``.

Connector resolution duplicates ~20 lines of the proven briefing glue
(``briefing/fetchers.py::fetch_agenda`` / ``_resolve_tasks_client``) rather
than importing its private helpers across domains — recorded trade-off. The
preference resolution it also performs is NOT duplicated: it goes through the
shared ``connectors/preferences/owner_defaults`` helper.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.domains.agents.constants import AGENT_PEER
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.peer.summaries import format_peer_availability, format_peer_tasks
from src.domains.agents.tools.decorators import read_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import get_user_preferences, validate_runtime_config
from src.domains.connectors.clients.registry import ClientRegistry
from src.domains.connectors.preferences.owner_defaults import (
    resolve_owner_calendar_id,
    resolve_owner_task_list_id,
)
from src.domains.connectors.provider_resolver import (
    find_error_connector_type,
    resolve_active_connector,
)
from src.domains.connectors.service import ConnectorService
from src.domains.peers.models import PeerShareDomain, PeerShareLevel
from src.domains.peers.repository import PeersRepository
from src.domains.shared.text_normalization import fold_name
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

_PEER_EVENTS_LOOKAHEAD_HOURS = 48
_PEER_EVENTS_MAX = 25
_PEER_TASKS_MAX = 25


async def _resolve_shared_peer(
    repo: PeersRepository,
    user_id: UUID,
    peer_name: str,
    domain: PeerShareDomain,
) -> tuple[Any | None, User | None, str | None, str]:
    """Resolve (connection, peer user, share level) for a named, sharing peer.

    Args:
        repo: Peers repository on the current session.
        user_id: The caller.
        peer_name: Peer display name (folded exact match on connections).
        domain: Domain the caller wants to read.

    Returns:
        (connection, peer ORM user, share level or None, failure_reason) —
        failure_reason is "" on success, else one of
        ``no_connection`` / ``not_shared`` / ``peer_inactive``.
    """
    from sqlalchemy import select

    connections = await repo.list_accepted_for_user(user_id)
    peer_ids = {(c.user_b_id if c.user_a_id == user_id else c.user_a_id): c for c in connections}
    if not peer_ids:
        return None, None, None, "no_connection"
    rows = (await repo.db.execute(select(User).where(User.id.in_(peer_ids.keys())))).scalars()
    folded = fold_name(peer_name)
    peer = next((u for u in rows if fold_name(u.full_name or "") == folded), None)
    if peer is None:
        return None, None, None, "no_connection"
    if not peer.is_active or peer.deleted_at:
        return None, None, None, "peer_inactive"
    connection = peer_ids[peer.id]
    shares = await repo.list_shares(connection.id)
    level = next(
        (s.level for s in shares if s.owner_user_id == peer.id and s.domain == domain.value),
        None,
    )
    if level is None:
        return connection, peer, None, "not_shared"
    return connection, peer, level, ""


async def _connector_failure(peer: User, category: str, noun: str) -> UnifiedToolOutput:
    """Typed failure for a peer whose provider could not be reached.

    Distinguishes the two states that used to share one sentence: a peer who
    never connected this capability, and a peer whose OAuth access BROKE. For
    the asking user they are different facts — the second resolves itself the
    moment the peer reconnects, and telling them "not connected" about someone
    who connected months ago reads as plainly false (measured 2026-07-30).
    Reuses ``find_error_connector_type`` (ADR-134 V2), the same predicate the
    connector-notice banner uses, rather than a second notion of "broken".

    Args:
        peer: The peer whose provider failed.
        category: Functional category ("calendar", "tasks").
        noun: How to name the capability to the asking user.

    Returns:
        A failure output naming the peer, never their connector type.
    """
    try:
        async with get_db_context() as db:
            broken = await find_error_connector_type(peer.id, category, ConnectorService(db))
    except Exception as exc:
        # This lookup only REFINES a failure that already happened. It must
        # never be able to turn a clean "not available" into a raised tool: a
        # database hiccup on the failure path would otherwise cost the whole
        # answer, which is strictly worse than the vaguer message below.
        logger.debug(
            "peer_connector_state_lookup_failed",
            error=str(exc),
            error_type=type(exc).__name__,
            category=category,
        )
        broken = None
    if broken:
        return UnifiedToolOutput.failure(
            message=(
                f"{peer.full_name}'s {noun} access is currently broken on their side "
                f"(it needs to be reconnected by them) — this is temporary and is not "
                f"about what they chose to share with you."
            ),
            error_code="NOT_AVAILABLE",
        )
    return UnifiedToolOutput.failure(
        message=f"{peer.full_name} has no connected {noun} right now.",
        error_code="NOT_AVAILABLE",
    )


def _share_failure(reason: str, peer_name: str) -> UnifiedToolOutput:
    """Typed failure for an unreadable peer domain."""
    messages = {
        "no_connection": (
            f"No accepted connection matches '{peer_name}'. "
            "Use list_peer_connections to see who you are connected to."
        ),
        "not_shared": (
            f"{peer_name} does not share this domain with you. "
            "They can enable it in their Connections settings."
        ),
        "peer_inactive": f"{peer_name} is not reachable at the moment.",
    }
    return UnifiedToolOutput.failure(
        message=messages.get(reason, "This peer data is not available."),
        error_code="NOT_FOUND" if reason == "no_connection" else "FORBIDDEN",
    )


async def _peer_calendar_events(peer: User) -> list[dict[str, Any]]:
    """List the peer's next-48h raw events (briefing fetch_agenda glue).

    Raises:
        LookupError: when the peer has no active calendar connector.
    """
    async with get_db_context() as db:
        connector_service = ConnectorService(db)
        resolved_type = await resolve_active_connector(peer.id, "calendar", connector_service)
        if resolved_type is None:
            raise LookupError("calendar_not_connected")
        credentials: Any = (
            await connector_service.get_apple_credentials(peer.id, resolved_type)
            if resolved_type.is_apple
            else await connector_service.get_connector_credentials(peer.id, resolved_type)
        )
        if not credentials:
            raise LookupError("calendar_not_connected")
        client_class = ClientRegistry.get_client_class(resolved_type)
        if client_class is None:
            raise LookupError("calendar_not_connected")
        client = client_class(peer.id, credentials, connector_service)
        # THE PEER's configured default calendar, not `primary`: their agenda
        # may well live in a named one, and every other read path in the
        # codebase honours this preference (briefing, calendar_tools,
        # tasks_tools). Reported 2026-07-30 — a peer with a 10:00 appointment
        # was reported free because only `primary` was read.
        calendar_id = await resolve_owner_calendar_id(
            db=db, client=client, owner_id=peer.id, connector_type=resolved_type
        )
        now = datetime.now(UTC)
        result = await client.list_events(
            time_min=now.isoformat(),
            time_max=(now + timedelta(hours=_PEER_EVENTS_LOOKAHEAD_HOURS)).isoformat(),
            max_results=_PEER_EVENTS_MAX,
            calendar_id=calendar_id,
            fields=["id", "summary", "start", "end"],
        )
    return result.get("items", []) or []


def _event_slot(event: dict[str, Any], include_title: bool) -> dict[str, Any]:
    """Map one raw event to a busy slot (title only at level ``details``)."""
    start = event.get("start") or {}
    end = event.get("end") or {}
    slot: dict[str, Any] = {
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
    }
    if include_title:
        slot["title"] = event.get("summary") or ""
    return slot


@read_tool(name="get_peer_availability", agent_name=AGENT_PEER)
async def get_peer_availability_tool(
    peer_name: Annotated[str, "Full name of the CONNECTED user whose availability to check"],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read a connected peer's calendar availability (their shared level).

    Reads the calendar the PEER configured as their default, not ``primary``.
    Level ``availability`` returns anonymous busy slots (free/busy only);
    level ``details`` adds event titles.

    The returned ``message`` is already rendered for the response model: hours
    converted to the ASKING user's timezone, all-day entries separated from
    real busy hours. ``structured_data`` keeps the raw slots in the peer's own
    frame for inter-step references.

    Args:
        peer_name: Display name among the caller's accepted connections.
        runtime: LangChain tool runtime (injected).

    Returns:
        UnifiedToolOutput with busy slots, peer timezone and share level.
    """
    validated = validate_runtime_config(runtime, "get_peer_availability_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    user_id = UUID(str(validated.user_id))

    async with get_db_context() as db:
        repo = PeersRepository(db)
        connection, peer, level, reason = await _resolve_shared_peer(
            repo, user_id, peer_name, PeerShareDomain.CALENDAR
        )
        if reason:
            return _share_failure(reason, peer_name)
        assert connection is not None and peer is not None and level is not None  # noqa: S101
        # Transparency BEFORE the provider call: the attempt itself is what
        # the owner is entitled to see (spec §12.4).
        await repo.log_access(
            accessor_id=user_id,
            owner_id=peer.id,
            connection_id=connection.id,
            domain=PeerShareDomain.CALENDAR.value,
            tool_name="get_peer_availability",
        )
        await db.commit()

    try:
        events = await _peer_calendar_events(peer)
    except LookupError:
        return await _connector_failure(peer, "calendar", "calendar")

    include_titles = level == PeerShareLevel.DETAILS.value
    slots = [_event_slot(event, include_titles) for event in events]
    viewer_timezone, _, _ = await get_user_preferences(runtime)
    logger.info(
        "peer_availability_read",
        accessor_id=str(user_id),
        owner_id=str(peer.id),
        slots=len(slots),
        level=level,
    )
    return UnifiedToolOutput.data_success(
        # The SLOTS themselves, not a sentence about them: `message` is
        # `summary_for_llm`, the only one of the three payloads the response
        # model ever reads. Shipping them in `structured_data` alone made the
        # assistant answer "I have no detail about his slots" while holding six
        # of them (defect 2026-07-30, request 2386ce1b).
        message=format_peer_availability(
            slots,
            peer_name=peer.full_name,
            share_level=level,
            viewer_timezone=viewer_timezone,
            lookahead_hours=_PEER_EVENTS_LOOKAHEAD_HOURS,
        ),
        structured_data={
            "peer_name": peer.full_name,
            "peer_timezone": peer.timezone,
            "share_level": level,
            "busy_slots": slots,
            "provenance": "peer_shared_data",
        },
    )


@read_tool(name="get_peer_tasks", agent_name=AGENT_PEER)
async def get_peer_tasks_tool(
    peer_name: Annotated[str, "Full name of the CONNECTED user whose tasks to read"],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read a connected peer's pending task titles (share level ``titles``).

    Args:
        peer_name: Display name among the caller's accepted connections.
        runtime: LangChain tool runtime (injected).

    Returns:
        UnifiedToolOutput with the peer's pending task titles.
    """
    validated = validate_runtime_config(runtime, "get_peer_tasks_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    user_id = UUID(str(validated.user_id))

    async with get_db_context() as db:
        repo = PeersRepository(db)
        connection, peer, level, reason = await _resolve_shared_peer(
            repo, user_id, peer_name, PeerShareDomain.TASK
        )
        if reason:
            return _share_failure(reason, peer_name)
        assert connection is not None and peer is not None and level is not None  # noqa: S101
        await repo.log_access(
            accessor_id=user_id,
            owner_id=peer.id,
            connection_id=connection.id,
            domain=PeerShareDomain.TASK.value,
            tool_name="get_peer_tasks",
        )
        await db.commit()

    try:
        titles = await _peer_task_titles(peer)
    except LookupError:
        return await _connector_failure(peer, "tasks", "task list")

    logger.info(
        "peer_tasks_read",
        accessor_id=str(user_id),
        owner_id=str(peer.id),
        tasks=len(titles),
    )
    return UnifiedToolOutput.data_success(
        # Same contract as the availability path: the titles, not a sentence
        # announcing that titles exist.
        message=format_peer_tasks(titles, peer_name=peer.full_name),
        structured_data={
            "peer_name": peer.full_name,
            "task_titles": titles,
            "provenance": "peer_shared_data",
        },
    )


async def _peer_task_titles(peer: User) -> list[str]:
    """List the peer's pending task titles (briefing _resolve_tasks_client glue).

    Raises:
        LookupError: when the peer has no active tasks connector.
    """
    async with get_db_context() as db:
        connector_service = ConnectorService(db)
        resolved_type = await resolve_active_connector(peer.id, "tasks", connector_service)
        if resolved_type is None:
            raise LookupError("tasks_not_connected")
        credentials = await connector_service.get_connector_credentials(peer.id, resolved_type)
        if not credentials:
            raise LookupError("tasks_not_connected")
        client_class = ClientRegistry.get_client_class(resolved_type)
        if client_class is None:
            raise LookupError("tasks_not_connected")
        client = client_class(peer.id, credentials, connector_service)
        # Same reasoning as the calendar path: the peer's own default list.
        task_list_id = await resolve_owner_task_list_id(
            db=db, client=client, owner_id=peer.id, connector_type=resolved_type
        )
        result = await client.list_tasks(task_list_id=task_list_id, max_results=_PEER_TASKS_MAX)
    tasks = result.get("items", []) or []
    return [
        task.get("title") or ""
        for task in tasks
        if task.get("status") == "needsAction" and task.get("title")
    ]
