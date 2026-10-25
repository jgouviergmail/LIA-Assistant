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

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.domains.agents.constants import AGENT_PEER
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.peer.name_directory import PeerNameOutcome, resolve_connected_peer
from src.domains.agents.peer.summaries import format_peer_availability, format_peer_tasks
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import read_tool
from src.domains.agents.tools.name_refusals import ambiguous_name_failure
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import get_user_preferences, validate_runtime_config
from src.domains.connectors.active_client import ActiveClient, open_active_client
from src.domains.connectors.calendar_access import CalendarAccess, open_active_calendar
from src.domains.connectors.preferences.owner_defaults import (
    TASK_LIST,
    resolve_owner_container_id,
)
from src.domains.connectors.provider_resolver import find_error_connector_type
from src.domains.connectors.service import ConnectorService
from src.domains.peers.models import PeerShareDomain, PeerShareLevel
from src.domains.peers.repository import PeersRepository
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

_PEER_EVENTS_LOOKAHEAD_HOURS = 48
_PEER_EVENTS_MAX = 25
_PEER_TASKS_MAX = 25

#: What the model reads about ``peer_name`` — the rule ``resolve_connected_peer``
#: applies, stated where the model fills the parameter.
_PEER_NAME_ARG = (
    "Name of the CONNECTED user as the person said it: the full name, or a "
    "first name when it designates one connection. Several people matching "
    "is answered with the candidates to ask about."
)


@dataclass(frozen=True)
class _Refusal:
    """Why a peer read cannot happen, and who to name in the refusal.

    Attributes:
        reason: ``no_connection`` / ``ambiguous`` / ``not_a_connection`` /
            ``not_shared`` / ``peer_inactive``.
        candidates: Display names to ask about or to name, bounded.
    """

    reason: str
    candidates: tuple[str, ...] = ()


#: The refusal each non-read outcome of the name resolution becomes.
_UNRESOLVED_REASONS: dict[PeerNameOutcome, str] = {
    PeerNameOutcome.AMBIGUOUS: "ambiguous",
    PeerNameOutcome.NOT_A_CONNECTION: "not_a_connection",
    PeerNameOutcome.UNKNOWN: "no_connection",
}


async def _resolve_shared_peer(
    repo: PeersRepository,
    user_id: UUID,
    peer_name: str,
    domain: PeerShareDomain,
) -> tuple[Any | None, User | None, str | None, _Refusal | None]:
    """Resolve (connection, peer user, share level) for a named, sharing peer.

    The name is resolved by ``resolve_connected_peer``: a first name reads the
    one connection it designates, and a name that also designates someone who
    is not connected is asked about rather than guessed.

    Args:
        repo: Peers repository on the current session.
        user_id: The caller.
        peer_name: The peer's name as the person said it.
        domain: Domain the caller wants to read.

    Returns:
        (connection, peer ORM user, share level or None, refusal) — refusal is
        None on success.
    """
    from sqlalchemy import select

    connections = await repo.list_accepted_for_user(user_id)
    peer_ids = {(c.user_b_id if c.user_a_id == user_id else c.user_a_id): c for c in connections}
    if not peer_ids:
        return None, None, None, _Refusal("no_connection")
    users = list(
        (await repo.db.execute(select(User).where(User.id.in_(peer_ids.keys())))).scalars()
    )
    # A partial name reads the relationship list, whose SMS senders can ask
    # the contacts provider: the reads end before that wait (ADR-304).
    await repo.db.commit()
    match = await resolve_connected_peer(
        user_id, peer_name, [(user.full_name or "", user.id) for user in users]
    )
    if match.outcome is not PeerNameOutcome.READ:
        logger.info(
            "peer_name_unresolved", outcome=match.outcome.value, named=len(match.candidates)
        )
        return None, None, None, _Refusal(_UNRESOLVED_REASONS[match.outcome], match.candidates)
    peer = next(user for user in users if user.id == match.peer_id)
    return await _shared_level(repo, peer_ids[peer.id], peer, domain)


async def _shared_level(
    repo: PeersRepository, connection: Any, peer: User, domain: PeerShareDomain
) -> tuple[Any | None, User | None, str | None, _Refusal | None]:
    """The level the resolved peer shares ``domain`` at, re-read at execution time.

    Args:
        repo: Peers repository on the current session.
        connection: The accepted connection with the peer.
        peer: The resolved peer.
        domain: Domain the caller wants to read.

    Returns:
        The same tuple as ``_resolve_shared_peer``.
    """
    if not peer.is_active or peer.deleted_at:
        return None, None, None, _Refusal("peer_inactive")
    shares = await repo.list_shares(connection.id)
    level = next(
        (s.level for s in shares if s.owner_user_id == peer.id and s.domain == domain.value),
        None,
    )
    if level is None:
        return connection, peer, None, _Refusal("not_shared")
    return connection, peer, level, None


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


#: The error code of each refusal; anything else is a share the peer withholds.
_REFUSAL_CODES: dict[str, str] = {
    "no_connection": ToolErrorCode.NOT_FOUND,
    "not_a_connection": ToolErrorCode.NOT_FOUND,
}


def _share_failure(refusal: _Refusal, peer_name: str) -> UnifiedToolOutput:
    """Typed failure for an unreadable peer domain."""
    if refusal.reason == "ambiguous":
        return ambiguous_name_failure(peer_name, refusal.candidates)
    named = ", ".join(refusal.candidates)
    messages = {
        "no_connection": (
            f"No accepted connection matches '{peer_name}'. "
            "Use list_peer_connections to see who you are connected to."
        ),
        "not_a_connection": (
            f"'{peer_name}' designates {named}, who is not a connected LIA user: "
            "none of their data can be read here. Answer from the user's own "
            "sources instead (calendar, e-mails, messages)."
        ),
        "not_shared": (
            f"{peer_name} does not share this domain with you. "
            "They can enable it in their Connections settings."
        ),
        "peer_inactive": f"{peer_name} is not reachable at the moment.",
    }
    return UnifiedToolOutput.failure(
        message=messages.get(refusal.reason, "This peer data is not available."),
        error_code=_REFUSAL_CODES.get(refusal.reason, ToolErrorCode.FORBIDDEN),
        metadata={"candidates": list(refusal.candidates)} if refusal.candidates else None,
    )


async def _peer_calendar_events(peer: User) -> list[dict[str, Any]]:
    """List the peer's next-48h raw events.

    Reads THE PEER's configured default calendar, not ``primary``: their
    agenda may well live in a named one, and every other read path honours
    this preference (reported 2026-07-30 — a peer with a 10:00 appointment was
    reported free because only ``primary`` was read). Opened through the shared
    door: no session held while the provider answers, the transport closed on
    every path (it never was here) — ADR-304.

    Raises:
        LookupError: when the peer has no usable calendar connector.
    """
    async with open_active_calendar(peer.id) as access:
        if not isinstance(access, CalendarAccess):
            raise LookupError("calendar_not_connected")
        now = datetime.now(UTC)
        result = await access.client.list_events(
            time_min=now.isoformat(),
            time_max=(now + timedelta(hours=_PEER_EVENTS_LOOKAHEAD_HOURS)).isoformat(),
            max_results=_PEER_EVENTS_MAX,
            calendar_id=access.calendar_id,
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
    peer_name: Annotated[str, _PEER_NAME_ARG],
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
        peer_name: The peer's name as the person said it (full or first name).
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
        connection, peer, level, refusal = await _resolve_shared_peer(
            repo, user_id, peer_name, PeerShareDomain.CALENDAR
        )
        if refusal is not None:
            return _share_failure(refusal, peer_name)
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
        # The SLOTS themselves, rendered in the asking user's timezone: the
        # manifest declares this message the tool's pipeline data channel
        # (ADR-347), because the raw slots below keep the peer's frame and
        # both would give the response model two clocks. Shipped in
        # `structured_data` alone, they once made the assistant answer "I have
        # no detail about his slots" while holding six of them (defect
        # 2026-07-30, request 2386ce1b).
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
    peer_name: Annotated[str, _PEER_NAME_ARG],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read a connected peer's pending task titles (share level ``titles``).

    Args:
        peer_name: The peer's name as the person said it (full or first name).
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
        connection, peer, level, refusal = await _resolve_shared_peer(
            repo, user_id, peer_name, PeerShareDomain.TASK
        )
        if refusal is not None:
            return _share_failure(refusal, peer_name)
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
    """List the peer's pending task titles, from THEIR default list.

    Same door and same reasoning as the calendar path (ADR-304).

    Raises:
        LookupError: when the peer has no usable tasks connector.
    """
    async with open_active_client("tasks", peer.id, container=TASK_LIST) as opened:
        if not isinstance(opened, ActiveClient):
            raise LookupError("tasks_not_connected")
        task_list_id = await resolve_owner_container_id(
            client=opened.client,
            name=opened.preferred_name,
            owner_id=peer.id,
            container=TASK_LIST,
        )
        result = await opened.client.list_tasks(
            task_list_id=task_list_id, max_results=_PEER_TASKS_MAX
        )
    tasks = result.get("items", []) or []
    return [
        task.get("title") or ""
        for task in tasks
        if task.get("status") == "needsAction" and task.get("title")
    ]
