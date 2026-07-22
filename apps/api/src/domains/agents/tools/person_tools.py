"""Person-360 overview tool (P3, ADR-141).

One call aggregates everything the assistant knows about a person across
domains: contact card (active contacts provider), recent emails, upcoming
shared events, and relevant long-term memories. Each sub-fetch runs with its
OWN session/client and its own failure boundary (briefing pattern) — the
overview is honestly PARTIAL (``partial_failures``) rather than
all-or-nothing. Read-only, no HITL.

Typical chains: "prépare mon call avec Marie", meeting preparation, the
``preparation-reunion`` skill.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.constants import GMAIL_FORMAT_METADATA
from src.domains.agents.constants import AGENT_CONTACT
from src.domains.agents.tools.decorators import read_tool, with_user_preferences
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    parse_user_id,
    validate_runtime_config,
)

logger = structlog.get_logger(__name__)

_RECENT_EMAILS_LIMIT = 5
_UPCOMING_EVENTS_DAYS = 30
_UPCOMING_EVENTS_LIMIT = 5
_MEMORIES_LIMIT = 5
_MEMORY_MIN_SCORE = 0.3


async def _resolve_provider_client(user_id: UUID, category: str) -> Any | None:
    """Resolve the active provider client for a category, or None.

    Same dynamic-resolution pattern as the heartbeat fetchers (Google /
    Apple / Microsoft). Opens and closes its own DB session — the returned
    client carries its own HTTP transport.

    Args:
        user_id: Owner user id.
        category: Functional category ("contacts", "email", "calendar").

    Returns:
        Instantiated provider client, or None when not configured.
    """
    from src.domains.connectors.clients.registry import ClientRegistry
    from src.domains.connectors.provider_resolver import resolve_active_connector
    from src.domains.connectors.service import ConnectorService
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        connector_service = ConnectorService(db)
        resolved_type = await resolve_active_connector(user_id, category, connector_service)
        if resolved_type is None:
            return None
        if getattr(resolved_type, "is_apple", False):
            credentials = await connector_service.get_apple_credentials(user_id, resolved_type)
        else:
            credentials = await connector_service.get_connector_credentials(user_id, resolved_type)
        if not credentials:
            return None
        client_class = ClientRegistry.get_client_class(resolved_type)
        if client_class is None:
            return None
        return client_class(user_id, credentials, connector_service)


def _values_of(person: dict[str, Any], field: str, key: str = "value") -> list[str]:
    """Extract the non-empty ``key`` values of a People API multi-valued field."""
    return [entry.get(key) for entry in (person.get(field) or []) if entry.get(key)]


def _person_to_card(person: dict[str, Any], fallback_name: str) -> dict[str, Any]:
    """Map a People API person payload to the compact overview card."""
    names = person.get("names", []) or []
    display = next((n.get("displayName") for n in names if n.get("displayName")), fallback_name)
    return {
        "name": display,
        "emails": _values_of(person, "emailAddresses"),
        "phones": _values_of(person, "phoneNumbers"),
        "organizations": _values_of(person, "organizations", key="name"),
    }


async def _fetch_contact_card(user_id: UUID, person_name: str) -> dict[str, Any] | None:
    """Resolve the person's contact card from the active contacts provider.

    Returns:
        Compact card dict, or None when unresolved / provider missing.
    """
    client = await _resolve_provider_client(user_id, "contacts")
    if client is None:
        return None
    try:
        result = await client.search_contacts(query=person_name, page_size=3)
    finally:
        await client.close()
    people = result.get("results", []) or result.get("connections", []) or []
    if not people:
        return None
    person = people[0].get("person", people[0])
    return _person_to_card(person, person_name)


async def _fetch_recent_emails(user_id: UUID, person_name: str) -> list[dict[str, str]] | None:
    """Last exchanges with the person from the active email provider."""
    client = await _resolve_provider_client(user_id, "email")
    if client is None:
        return None
    emails: list[dict[str, str]] = []
    try:
        result = await client.search_emails(
            query=person_name, max_results=_RECENT_EMAILS_LIMIT, use_cache=True
        )
        messages = result.get("messages", []) or []
        for msg in messages:
            if set(msg.keys()) <= {"id", "threadId"}:
                full = await client.get_message(
                    msg["id"], format=GMAIL_FORMAT_METADATA, use_cache=True
                )
                if full:
                    msg = full
            emails.append(
                {
                    "subject": msg.get("subject", ""),
                    "from": msg.get("from", ""),
                    "date": str(msg.get("internalDate", "")),
                    "snippet": (msg.get("snippet") or "")[:160],
                }
            )
    finally:
        await client.close()
    return emails


async def _fetch_upcoming_events(user_id: UUID, person_name: str) -> list[dict[str, Any]] | None:
    """Upcoming events mentioning the person (next N days)."""
    client = await _resolve_provider_client(user_id, "calendar")
    if client is None:
        return None
    now = datetime.now(UTC)
    try:
        result = await client.list_events(
            time_min=now.isoformat(),
            time_max=(now + timedelta(days=_UPCOMING_EVENTS_DAYS)).isoformat(),
            max_results=_UPCOMING_EVENTS_LIMIT,
            query=person_name,
            fields=["id", "summary", "start", "end", "location", "attendees"],
        )
    finally:
        await client.close()
    return [
        {
            "title": e.get("summary", "Untitled"),
            "start": (e.get("start") or {}).get("dateTime") or (e.get("start") or {}).get("date"),
            "location": e.get("location"),
        }
        for e in result.get("items", []) or []
    ]


async def _fetch_person_memories(user_id: UUID, person_name: str) -> list[str] | None:
    """Long-term memories relevant to the person (embedding + topic match)."""
    from src.domains.memories.repository import MemoryRepository
    from src.infrastructure.database.session import get_db_context
    from src.infrastructure.llm.user_message_embedding import get_or_compute_embedding

    query_embedding = await get_or_compute_embedding(message=person_name)
    if not query_embedding:
        return None
    async with get_db_context() as db:
        results = await MemoryRepository(db).search_by_relevance(
            user_id=user_id,
            query_embedding=query_embedding,
            limit=_MEMORIES_LIMIT,
            min_score=_MEMORY_MIN_SCORE,
        )
    return [memory.content for memory, _score in results if memory.content]


@read_tool(name="get_person_overview", agent_name=AGENT_CONTACT)
@with_user_preferences
async def get_person_overview_tool(
    person_name: Annotated[
        str,
        "Person to build the 360° overview for: a contact name as the user "
        "says it ('Marie', 'Marie Dupont', 'mon frère' AFTER memory resolution).",
    ],
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    user_timezone: str = "UTC",
    locale: str = "fr",
) -> UnifiedToolOutput:
    """Cross-domain 360° overview of a person (contact + emails + events + memories).

    Args:
        person_name: Person to resolve and aggregate.
        runtime: LangChain tool runtime.
        user_timezone: Injected user timezone (preference contract).
        locale: Injected user language (preference contract).

    Returns:
        UnifiedToolOutput with ``{contact, recent_emails, upcoming_events,
        memories, partial_failures}`` — honestly partial on sub-failures.
    """
    config = validate_runtime_config(runtime, "get_person_overview_tool")
    if isinstance(config, UnifiedToolOutput):
        return config
    user_id = parse_user_id(config.user_id)

    results = await asyncio.gather(
        _fetch_contact_card(user_id, person_name),
        _fetch_recent_emails(user_id, person_name),
        _fetch_upcoming_events(user_id, person_name),
        _fetch_person_memories(user_id, person_name),
        return_exceptions=True,
    )
    labels = ("contact", "emails", "events", "memories")
    partial_failures: list[str] = []
    resolved: dict[str, Any] = {}
    for label, result in zip(labels, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning(
                "person_overview_subfetch_failed",
                block=label,
                error=str(result),
            )
            partial_failures.append(label)
            resolved[label] = None
        else:
            resolved[label] = result

    contact = resolved["contact"]
    if contact is None and "contact" not in partial_failures:
        return UnifiedToolOutput.failure(
            message=f"no contact found matching '{person_name}'",
            error_code="person_not_found",
        )

    return UnifiedToolOutput.data_success(
        message=f"overview built for {person_name}"
        + (f" (partial: {', '.join(partial_failures)} unavailable)" if partial_failures else ""),
        structured_data={
            "contact": contact or {"name": person_name},
            "recent_emails": resolved["emails"] or [],
            "upcoming_events": resolved["events"] or [],
            "memories": resolved["memories"] or [],
            "partial_failures": partial_failures,
        },
    )
