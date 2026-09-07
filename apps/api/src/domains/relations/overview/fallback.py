"""The by-name last resort, for a person with no address on their card.

The address path is the exact one and it is tried first. But a person the
address book holds no mailbox for would otherwise come back with nothing at
all — so the old by-name search runs, and its results are FLAGGED
(``*_matched_by_name``). That flag is the whole point: matching a person's name
against MIME headers and event text finds strangers and misses real threads, so
the assistant must be able to say "found by name, possibly incomplete or
off-target" instead of presenting it as fact.

The provider client comes from ``providers.client.open_category_client`` — the
module that already owns "resolve the active connector, instantiate it, close
its transport on every path". This file used to carry its own copy of that
resolution, which closed the client in a ``finally`` of its own and left it open
whenever resolution itself failed halfway.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from src.core.constants import GMAIL_FORMAT_METADATA
from src.domains.relations.overview_scope import OverviewSection, RelationOverviewScope
from src.domains.relations.providers.client import ProviderNotConfigured, open_category_client
from src.domains.relations.providers.schemas import ContextStatus, RelationContext

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.get_logger(__name__)

_RECENT_EMAILS_LIMIT = 5
_UPCOMING_EVENTS_DAYS = 30
_UPCOMING_EVENTS_LIMIT = 5


async def fetch_recent_emails(user_id: UUID, person_name: str) -> list[dict[str, str]] | None:
    """Last exchanges with the person, searched by NAME on the active provider.

    Args:
        user_id: Owner of the mailbox.
        person_name: The name to search for.

    Returns:
        The messages found, or None when no email connector is usable.
    """
    emails: list[dict[str, str]] = []
    try:
        async with open_category_client("email", user_id) as opened:
            client = opened.client
            result = await client.search_emails(
                query=person_name, max_results=_RECENT_EMAILS_LIMIT, use_cache=True
            )
            for message in result.get("messages", []) or []:
                if set(message.keys()) <= {"id", "threadId"}:
                    full = await client.get_message(
                        message["id"], format=GMAIL_FORMAT_METADATA, use_cache=True
                    )
                    if full:
                        message = full
                emails.append(
                    {
                        "subject": message.get("subject", ""),
                        "from": message.get("from", ""),
                        "date": str(message.get("internalDate", "")),
                        "snippet": (message.get("snippet") or "")[:160],
                    }
                )
    except ProviderNotConfigured:
        return None
    return emails


async def fetch_upcoming_events(user_id: UUID, person_name: str) -> list[dict[str, Any]] | None:
    """Upcoming events mentioning the person (next 30 days).

    Args:
        user_id: Owner of the calendar.
        person_name: The name to search for.

    Returns:
        The events found, or None when no calendar connector is usable.
    """
    now = datetime.now(UTC)
    try:
        async with open_category_client("calendar", user_id) as opened:
            result = await opened.client.list_events(
                time_min=now.isoformat(),
                time_max=(now + timedelta(days=_UPCOMING_EVENTS_DAYS)).isoformat(),
                max_results=_UPCOMING_EVENTS_LIMIT,
                query=person_name,
                fields=["id", "summary", "start", "end", "location", "attendees"],
            )
    except ProviderNotConfigured:
        return None
    return [
        {
            "title": event.get("summary", "Untitled"),
            "start": (event.get("start") or {}).get("dateTime")
            or (event.get("start") or {}).get("date"),
            "location": event.get("location"),
        }
        for event in result.get("items", []) or []
    ]


async def fill_by_name(
    blocks: dict[str, Any],
    unavailable: list[str],
    user_id: UUID,
    person_name: str,
    scope: RelationOverviewScope,
    context: RelationContext,
) -> list[str]:
    """Fill the sections an absent address left empty, and flag what it found.

    Only ``no_address`` triggers it. A provider that is absent or broken is a
    different answer, and retrying it by name would answer a question nobody
    could ask — and would present a provider outage as data.

    Args:
        blocks: Payload being assembled, mutated in place.
        unavailable: Sections that could not be read.
        user_id: Owner.
        person_name: The name to fall back on.
        scope: What the reader ticked.
        context: The provider half, for the per-section statuses.

    Returns:
        The remaining unavailable sections (those the fallback did not fill).
    """
    remaining = list(unavailable)
    fallbacks = (
        (OverviewSection.EMAILS, "emails", fetch_recent_emails, context.emails),
        (OverviewSection.EVENTS, "events", fetch_upcoming_events, context.events),
    )
    for section, key, fetcher, payload in fallbacks:
        if section.value not in remaining or not scope.includes(section):
            continue
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
