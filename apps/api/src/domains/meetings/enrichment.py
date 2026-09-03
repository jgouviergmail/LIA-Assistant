"""Best-effort enrichment of a meeting: overlapping calendar event, place label (ADR-258).

Both helpers return ``None`` instead of raising: a meeting without a calendar
connector or without a Google key still gets its minutes. The calendar event's
title and attendees reach the synthesis prompt as HINTS only (the prompt says
so) — nothing here decides who spoke.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

#: Events considered around the recording (a meeting often starts late).
_CALENDAR_MARGIN = timedelta(minutes=30)
_MAX_EVENTS = 20


@dataclass(frozen=True)
class CalendarMatch:
    """The calendar event that overlapped the recording the most."""

    event_id: str
    provider: str
    title: str | None
    attendees: list[str] = field(default_factory=list)
    location: str | None = None


def _parse_when(value: dict[str, Any] | None) -> datetime | None:
    raw = (value or {}).get("dateTime") or (value or {}).get("date")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def best_overlap(
    events: list[dict[str, Any]], started_at: datetime, stopped_at: datetime
) -> dict[str, Any] | None:
    """The event overlapping ``[started_at, stopped_at]`` the longest (pure)."""
    best: tuple[float, dict[str, Any]] | None = None
    for event in events:
        start = _parse_when(event.get("start"))
        end = _parse_when(event.get("end"))
        if start is None or end is None or end <= start:
            continue
        overlap = (min(end, stopped_at) - max(start, started_at)).total_seconds()
        if overlap <= 0:
            continue
        if best is None or overlap > best[0]:
            best = (overlap, event)
    return best[1] if best else None


def _attendee_names(event: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for attendee in event.get("attendees") or []:
        if not isinstance(attendee, dict):
            continue
        label = attendee.get("displayName") or attendee.get("email")
        if label and label not in names:
            names.append(str(label))
    return names


async def match_calendar_event(
    db: AsyncSession, *, user_id: UUID, started_at: datetime, stopped_at: datetime
) -> CalendarMatch | None:
    """The user's calendar event overlapping the recording, if any (never raises)."""
    try:
        from src.domains.connectors.clients.registry import ClientRegistry
        from src.domains.connectors.preferences.owner_defaults import resolve_owner_calendar_id
        from src.domains.connectors.provider_resolver import resolve_active_connector
        from src.domains.connectors.service import ConnectorService

        connector_service = ConnectorService(db)
        resolved_type = await resolve_active_connector(user_id, "calendar", connector_service)
        if resolved_type is None:
            return None
        credentials = (
            await connector_service.get_apple_credentials(user_id, resolved_type)
            if resolved_type.is_apple
            else await connector_service.get_connector_credentials(user_id, resolved_type)
        )
        if not credentials:
            return None
        client_class = ClientRegistry.get_client_class(resolved_type)
        if client_class is None:
            return None
        client = client_class(user_id, credentials, connector_service)
        calendar_id = await resolve_owner_calendar_id(
            db=db, client=client, owner_id=user_id, connector_type=resolved_type
        )
        result = await client.list_events(
            time_min=(started_at - _CALENDAR_MARGIN).isoformat(),
            time_max=(stopped_at + _CALENDAR_MARGIN).isoformat(),
            max_results=_MAX_EVENTS,
            calendar_id=calendar_id,
            fields=["id", "summary", "start", "end", "attendees", "location"],
        )
        events = result.get("items", []) or []
    except (TimeoutError, httpx.HTTPError, ValueError, KeyError, AttributeError, OSError) as exc:
        logger.debug("meeting_calendar_match_failed", user_id=str(user_id), error=str(exc))
        return None

    event = best_overlap(events, started_at, stopped_at)
    if event is None or not event.get("id"):
        return None
    return CalendarMatch(
        event_id=str(event["id"]),
        provider=str(getattr(resolved_type, "value", resolved_type)),
        title=str(event["summary"]) if event.get("summary") else None,
        attendees=_attendee_names(event),
        location=str(event["location"]) if event.get("location") else None,
    )


async def place_label(lat: float, lon: float, *, language: str) -> str | None:
    """A short address for the recording position, or ``None`` (never raises)."""
    try:
        from src.domains.connectors.clients.google_geocoding_helpers import reverse_geocode

        return await reverse_geocode(lat, lon, language=language)
    except (TimeoutError, httpx.HTTPError, ValueError, KeyError, OSError) as exc:
        logger.debug("meeting_reverse_geocode_failed", error=str(exc))
        return None
