"""Person-360 overview tool (P3, ADR-141 — rebuilt on the CRM services).

One call aggregates everything the assistant knows about a person: the
database-local half the personal CRM already owns (open commitments, calls,
relayed messages), the provider-backed half (contact card, mail exchanged,
meetings shared), and the long-term memories that are ABOUT the person —
semantically, which is this tool's own read and why it differs from the page's
literal name match.

**It searches by ADDRESS first.** The original version asked the mail
provider for the person's NAME and the calendar for a text query; both are
unreliable — a mail search matches MIME headers, and ``list_events(query=)``
has no cross-provider parity nor any notion of "this person is an attendee".
It now delegates to the two services the Relations page uses, which resolve
the person's ADDRESSES from the user's own address book and query by those.
The page and the assistant therefore answer from the SAME reads — including
the same Redis cache, so a 360° asked right after opening the card costs no
provider call at all.

The by-name search survives as the **fallback of last resort**: with no
address on the contact card, an empty answer would be worse than an imprecise
one. Its results are FLAGGED (``*_matched_by_name``) so the assistant can say
they may be incomplete or off-target rather than present them as fact.

The SCOPE is not inferred from the request. The chat link carries prose, so
the user's selection is written server-side before the chat opens and read
back here (``RelationOverviewScope``): what they ticked is what the assistant
gets, whatever the sentence says.

Each half keeps its own failure boundary — the overview is honestly PARTIAL
rather than all-or-nothing. Read-only, no HITL.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
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
from src.domains.relations.overview_scope import (
    OverviewDirection,
    OverviewSection,
    RelationOverviewScope,
)
from src.domains.relations.providers.schemas import (
    ContactCard,
    ContactValue,
    ContextStatus,
    RelationContext,
)
from src.domains.relations.providers.service import RelationContextService
from src.domains.relations.schemas import RelationDetail
from src.domains.relations.service import RelationsService

logger = structlog.get_logger(__name__)

#: The three sections that come from a connector, in payload order.
_PROVIDER_SECTIONS = (
    OverviewSection.CONTACT,
    OverviewSection.EMAILS,
    OverviewSection.EVENTS,
)


#: Semantic memory recall stays this tool's own read, deliberately different
#: from the page's literal `ILIKE`: the page answers "which memories MENTION
#: this name" (and says it is best-effort), the assistant benefits from
#: memories that are ABOUT the person without naming them.
_MEMORIES_LIMIT = 5
_MEMORY_MIN_SCORE = 0.3


async def _fetch_person_memories(user_id: UUID, person_name: str) -> list[str] | None:
    """Long-term memories relevant to the person (embedding + topic match)."""
    from src.domains.memories.repository import MemoryRepository
    from src.infrastructure.database.session import get_db_context
    from src.infrastructure.llm.user_message_embedding import get_or_compute_embedding

    # A person name is a lookup key, never an utterance: the triviality patterns
    # collide with real surnames (Fine, Cool, Bien), and treating one as trivial
    # returned None here — silently erasing that contact's memories.
    query_embedding = await get_or_compute_embedding(message=person_name, is_conversational=False)
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


#: The by-name path, kept ONLY as the fallback of last resort (see
#: `_fill_by_name`): a person with no address on their contact card would
#: otherwise get an empty answer. Its results are always flagged.
_RECENT_EMAILS_LIMIT = 5
_UPCOMING_EVENTS_DAYS = 30
_UPCOMING_EVENTS_LIMIT = 5


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


async def _nothing() -> None:
    """Placeholder for a block the reader excluded — keeps the gather shape."""
    return None


def _directions(scope: RelationOverviewScope) -> set[str]:
    """Directions the reader kept — mail and relayed messages share them."""
    return {direction.value for direction in scope.directions}


def _local_blocks(detail: RelationDetail, scope: RelationOverviewScope) -> dict[str, Any]:
    """The database-local half, filtered by what the reader ticked.

    Each list is a PAGE, and every page ships its EXACT total (ADR-185): the
    totals come from database aggregates over the whole set, so five rows out
    of a hundred and thirty-seven can be said as such. Without them the
    assistant reads five rows and states "you have five open commitments" —
    the same under-report the CRM cards were fixed for, one surface later.

    The relayed messages are the exception, and deliberately: the direction
    filter narrows the LIST but not the stored total, so a total would then
    describe a different set than the rows beside it. No total is the honest
    answer there — an inexact count must not exist.
    """
    blocks: dict[str, Any] = {}
    if scope.includes(OverviewSection.OPEN_LOOPS):
        blocks["open_commitments"] = [
            {
                "subject": loop.subject,
                "direction": loop.direction,
                "days_open": loop.days_open,
                # The DEADLINE, when one was captured. "What should I raise
                # next" is answered by what is due, so dropping it left the
                # most actionable field of the payload on the floor. Absent
                # rather than null: most commitments have none, and a key full
                # of nulls trains the model to mention them.
                **({"due_hint": loop.due_hint.isoformat()} if loop.due_hint else {}),
            }
            for loop in detail.open_loops[: scope.max_items]
        ]
        blocks["open_commitments_total"] = detail.open_loops_total
    if scope.includes(OverviewSection.CALLS):
        blocks["recent_calls"] = [
            {
                "objective": call.objective,
                "outcome": call.outcome,
                "summary": call.summary,
                # WHEN, like every other interaction in this payload. Without
                # it the assistant cannot place a call in time, and a request
                # about "recent interactions" walked straight past four of
                # them (production, 2026-08-01) — the one block that carried
                # no instant was the one block that went unused.
                "occurred_at": call.created_at.isoformat(),
            }
            for call in detail.recent_calls[: scope.max_items]
        ]
        blocks["recent_calls_total"] = detail.recent_calls_total
    if scope.includes(OverviewSection.PEER_MESSAGES):
        wanted = _directions(scope)
        blocks["relayed_messages"] = [
            {
                "direction": message.direction,
                "text": message.content,
                "occurred_at": message.occurred_at.isoformat(),
            }
            for message in detail.peer_messages
            if message.direction in wanted
        ][: scope.max_items]
        if len(wanted) == len(OverviewDirection):
            # Unfiltered: the stored total describes exactly these rows.
            blocks["relayed_messages_total"] = detail.peer_messages_total
    return blocks


def _labelled(values: Sequence[ContactValue]) -> list[str]:
    """Flatten labelled values, keeping the label that makes them legible.

    "Claire Lefèvre" alone does not say she is his spouse, and a phone number
    without "mobile" is one the assistant cannot choose between. The label is
    dropped only when the provider stored none.
    """
    return [f"{item.value} ({item.label})" if item.label else item.value for item in values]


def _card_block(card: ContactCard) -> dict[str, Any]:
    """The address-book entry, as the assistant reads it.

    The SAME content the card shows on screen — asking "what do you know about
    this person" and reading their file must not produce two different answers.
    Empty blocks are dropped rather than sent as ``[]``: a provider that stores
    no relations says nothing about whether this person has any, and a listed
    empty key invites the model to conclude one way (ADR-184).
    """
    fields: dict[str, Any] = {
        "display_name": card.display_name,
        "nickname": card.nickname,
        "organization": card.organization,
        "occupation": card.occupation,
        "birthday": card.birthday,
        "biography": card.biography,
        # Addresses stay bare: they are long, and "home"/"work" adds little to
        # a string that already names a street and a city.
        "emails": [email.value for email in card.emails],
        "addresses": [address.value for address in card.addresses],
        "links": [link.value for link in card.links],
        "phones": _labelled(card.phones),
        "relations": _labelled(card.relations),
        "important_dates": _labelled(card.important_dates),
        "messaging": _labelled(card.messaging),
    }
    return {key: value for key, value in fields.items() if value}


def _mail_block(context: RelationContext, scope: RelationOverviewScope) -> dict[str, Any]:
    """Mail exchanged, in the reader's chosen directions, plus its window."""
    wanted = _directions(scope)
    return {
        "emails": [
            # `excerpt` is omitted, never null, when the provider returned no
            # preview: a key present with no value invites the assistant to
            # describe a message it has not read.
            {
                key: value
                for key, value in (
                    ("direction", email.direction),
                    ("subject", email.subject),
                    (
                        "occurred_at",
                        email.occurred_at.isoformat() if email.occurred_at else None,
                    ),
                    ("excerpt", email.excerpt),
                )
                if value is not None
            }
            for email in context.emails.emails
            if email.direction in wanted
        ][: scope.max_items],
        # The scope, never a total: a provider page proves none (ADR-185).
        "emails_window_days": context.email_window_days,
    }


def _meeting_block(context: RelationContext, scope: RelationOverviewScope) -> dict[str, Any]:
    """Meetings shared, in the reader's chosen roles, plus their window."""
    wanted_roles = {role.value for role in scope.roles}
    return {
        "events": [
            {
                "summary": event.summary,
                "role": event.role if event.organizer_known else "unknown",
                "starts_at": event.starts_at.isoformat() if event.starts_at else None,
                "ends_at": event.ends_at.isoformat() if event.ends_at else None,
                "is_past": event.is_past,
            }
            for event in context.events.events
            # A role nobody verified must not be filtered ON: under a provider
            # that exposes no organizer, filtering by role would silently drop
            # every meeting instead of admitting the distinction is unknown.
            if not event.organizer_known or event.role in wanted_roles
        ][: scope.max_items],
        "events_window_days": context.window_days,
    }


def _peer_connection(detail: RelationDetail) -> dict[str, Any] | None:
    """The LIA connection behind this relationship, when there is one.

    Root-level context, NOT a scoped section: "you are connected since May,
    they share their availability, you share your task titles" describes the
    RELATIONSHIP, the way `identity_confidence` does — it is not a source of
    items a scope could narrow. It also costs nothing: the same `build_detail`
    read already carries it, and a 360° on a connected peer that never says
    they are one omits the most relevant fact on the card.
    """
    link = detail.peer_link
    if link is None:
        return None
    block: dict[str, Any] = {
        "shared_by_me": [f"{s.domain}:{s.level}" for s in link.shared_by_me],
        "shared_with_me": [f"{s.domain}:{s.level}" for s in link.shared_with_me],
    }
    if link.connected_since:
        block["connected_since"] = link.connected_since.isoformat()
    return block


def _recalled_memories(recall: object) -> list[str] | None:
    """What the semantic recall actually answered — or None for "I could not".

    ``None`` is not ``[]``: the recall returns None when no embedding could be
    computed (provider down, key missing), and an exception means the same.
    Flattening either into an empty list would have the assistant state this
    person is unmemorable — the negative ADR-184 forbids.
    """
    if isinstance(recall, BaseException) or recall is None:
        logger.info(
            "person_overview_memories_unreadable",
            error_type=type(recall).__name__ if recall is not None else "no_embedding",
        )
        return None
    return list(recall) if isinstance(recall, list) else []


#: Statuses that mean "the question was never answered" — a missing connector,
#: a failed read, an identity with no address. Never "there is nothing".
_UNREADABLE = frozenset(
    {ContextStatus.ERROR, ContextStatus.NOT_CONFIGURED, ContextStatus.NO_ADDRESS}
)


def _provider_blocks(context: RelationContext, scope: RelationOverviewScope) -> dict[str, Any]:
    """The provider-backed half, filtered the same way.

    A section that could not be READ carries no block at all. Emitting
    ``"emails": []`` next to ``unavailable: ["emails"]`` states both "nothing
    found" and "I could not look" in the same payload — and the model believes
    the list, because a list is data and the other is a caveat (ADR-184).
    """
    blocks: dict[str, Any] = {}
    if scope.includes(OverviewSection.CONTACT) and context.contact.contact is not None:
        blocks["contact"] = _card_block(context.contact.contact)
    if scope.includes(OverviewSection.EMAILS) and context.emails.status not in _UNREADABLE:
        blocks.update(_mail_block(context, scope))
    if scope.includes(OverviewSection.EVENTS) and context.events.status not in _UNREADABLE:
        blocks.update(_meeting_block(context, scope))
    return blocks


def _unavailable(context: RelationContext, scope: RelationOverviewScope) -> list[str]:
    """Sections the reader asked for that could not be read.

    Stated rather than silently empty: "I could not look" and "there is
    nothing" are different answers (ADR-184), and only the first is worth the
    assistant mentioning.
    """
    payloads = (context.contact, context.emails, context.events)
    return [
        section.value
        for section, payload in zip(_PROVIDER_SECTIONS, payloads, strict=True)
        if scope.includes(section) and payload.status in _UNREADABLE
    ]


async def _fill_by_name(
    blocks: dict[str, Any],
    unavailable: list[str],
    user_id: UUID,
    person_name: str,
    scope: RelationOverviewScope,
    context: RelationContext,
) -> list[str]:
    """Last resort when the contact card carries no address.

    The address path is the exact one, and it is tried first. But a person with
    no address on their card would otherwise come back with nothing at all —
    so rather than an empty answer, the OLD by-name search runs and its results
    are FLAGGED (``*_matched_by_name``). That flag is the whole point: matching
    a person's name against MIME headers and event text finds strangers and
    misses real threads, so the assistant must be able to say "found by name,
    possibly incomplete or off-target" instead of presenting it as fact.

    Only ``no_address`` triggers it. A provider that is absent or broken is a
    different answer, and retrying it by name would answer a question nobody
    could ask.

    Args:
        blocks: Payload being assembled, mutated in place.
        unavailable: Sections that could not be read.
        user_id: Owner.
        person_name: The name to fall back on.
        scope: What the reader ticked.

    Returns:
        The remaining unavailable sections (those the fallback did not fill).
    """
    remaining = list(unavailable)
    fallbacks = (
        (OverviewSection.EMAILS, "emails", _fetch_recent_emails, context.emails),
        (OverviewSection.EVENTS, "events", _fetch_upcoming_events, context.events),
    )
    for section, key, fetcher, payload in fallbacks:
        if section.value not in remaining or not scope.includes(section):
            continue
        # ONLY a missing address. A connector that is absent or broken is a
        # different answer, and retrying it by name would answer a question
        # nobody could ask — and would present a provider outage as data.
        if payload.status is not ContextStatus.NO_ADDRESS:
            continue
        try:
            found = await fetcher(user_id, person_name)
        except Exception as exc:  # noqa: BLE001 — a last resort never raises
            logger.info(
                "person_overview_name_fallback_failed",
                block=key,
                error_type=type(exc).__name__,
            )
            continue
        if not found:
            continue
        blocks[key] = found[: scope.max_items]
        blocks[f"{key}_matched_by_name"] = True
        remaining.remove(section.value)
        logger.info("person_overview_name_fallback_used", user_id=str(user_id), block=key)
    return remaining


def _overview_message(payload: dict[str, Any]) -> str:
    """The overview, in the field the response synthesizer actually reads.

    Measured on the dev API, 2026-08-01: the tool ran, produced relayed
    messages, commitments and memories — and the assistant answered *"I have no
    data at hand"*. Its payload had reached ``structured_data`` and stopped
    there. Only two channels reach the response prompt: the **data registry**,
    fed exclusively by tools declaring a ``context_key``, and this ``message``
    field (``formatters/agent_results._extract_action_success_messages``). This
    tool has no ``context_key`` — deliberately: the registry serialises ITEMS
    for filtering, one truncated line each, which is the wrong shape for one
    person's briefing across nine heterogeneous blocks. So the message carried
    ``"overview built for X"``: proof the tool ran, and not one fact.

    Serialised as compact JSON, like the planner catalogue: lossless, and it
    preserves the distinction the whole design rests on — a block that could
    not be read carries NO key and is named in ``unavailable``, while an empty
    list means "looked, found nothing" (ADR-190).

    Args:
        payload: The overview payload, exactly as ``structured_data`` carries it.

    Returns:
        A one-line header plus the payload as compact JSON.
    """
    person = payload.get("person", "")
    unavailable = payload.get("unavailable") or []
    # The gap is stated in the HEADER, not left to be inferred from a key
    # buried in the payload: "could not read" and "read and found nothing" are
    # the distinction the whole design rests on (ADR-190), and it is the one a
    # model is most likely to flatten when it is not said plainly.
    gap = f" (could not read: {', '.join(unavailable)})" if unavailable else ""
    return f"360 overview for {person}{gap}:\n" + json.dumps(
        payload, separators=(",", ":"), ensure_ascii=False, default=str
    )


def _overview_payload(
    detail: RelationDetail, blocks: dict[str, Any], unavailable: list[str]
) -> dict[str, Any]:
    """The tool's answer: who this is, then what was read about them.

    Identity and relationship context first — the name, how confidently it was
    matched, whether this person is a connected LIA user and what the two
    sides share — then the scoped blocks, then what could NOT be read.
    """
    connection = _peer_connection(detail)
    return {
        "person": detail.display_name,
        "identity_confidence": detail.identity_confidence.value,
        "is_peer": detail.is_peer,
        **({"peer_connection": connection} if connection else {}),
        **blocks,
        "unavailable": unavailable,
    }


@read_tool(name="get_person_overview", agent_name=AGENT_CONTACT)
@with_user_preferences
async def get_person_overview_tool(
    person_name: Annotated[
        str,
        "Person to build the 360 overview for: a relationship name as the user "
        "says it (Marie, Marie Dupont, or a nickname already resolved).",
    ],
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    user_timezone: str = "UTC",
    locale: str = "fr",
) -> UnifiedToolOutput:
    """360° overview of ONE person, across the CRM and the connected accounts.

    Reads exactly what the user selected on the relationship card — the scope
    is stored server-side, never inferred from the request's wording.

    Args:
        person_name: Person to resolve and aggregate.
        runtime: LangChain tool runtime.
        user_timezone: Injected user timezone (preference contract).
        locale: Injected user language (preference contract).

    Returns:
        UnifiedToolOutput with the selected blocks plus ``unavailable`` —
        honestly partial rather than silently empty.
    """
    config = validate_runtime_config(runtime, "get_person_overview_tool")
    if isinstance(config, UnifiedToolOutput):
        return config
    user_id = parse_user_id(config.user_id)

    service = RelationsService(user_id)
    scope = await service.get_overview_scope()

    # Two independent reads, each with its own session and failure boundary.
    wants_memories = scope.includes(OverviewSection.MEMORIES)
    detail, context, memories = await asyncio.gather(
        service.build_detail(person_name),
        RelationContextService(user_id).build(person_name),
        _fetch_person_memories(user_id, person_name) if wants_memories else _nothing(),
        return_exceptions=True,
    )
    if isinstance(detail, BaseException):
        logger.warning("person_overview_detail_failed", error_type=type(detail).__name__)
        return UnifiedToolOutput.failure(
            message=f"could not read the relationship '{person_name}'",
            error_code="person_overview_unavailable",
        )

    blocks = _local_blocks(detail, scope)
    recalled = _recalled_memories(memories) if wants_memories else []
    unreadable_memories = wants_memories and recalled is None
    if recalled is not None and wants_memories:
        blocks["memories"] = recalled
    if isinstance(context, BaseException):
        logger.warning("person_overview_context_failed", error_type=type(context).__name__)
        unavailable = [section.value for section in _PROVIDER_SECTIONS if scope.includes(section)]
    else:
        blocks |= _provider_blocks(context, scope)
        unavailable = _unavailable(context, scope)
        unavailable = await _fill_by_name(blocks, unavailable, user_id, person_name, scope, context)
    if unreadable_memories:
        unavailable.append(OverviewSection.MEMORIES.value)

    logger.info(
        "person_overview_built",
        user_id=str(user_id),
        blocks=sorted(blocks),
        unavailable=unavailable,
    )
    payload = _overview_payload(detail, blocks, unavailable)
    return UnifiedToolOutput.data_success(
        message=_overview_message(payload),
        structured_data=payload,
    )
