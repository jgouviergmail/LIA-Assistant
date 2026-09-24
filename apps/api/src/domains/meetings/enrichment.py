"""Best-effort enrichment of a meeting: overlapping calendar event, place label (ADR-258).

Both helpers return ``None`` instead of raising: a meeting without a calendar
connector or without a Google key still gets its minutes. The calendar event's
title and attendees reach the synthesis prompt as HINTS only (the prompt says
so) — nothing here decides who spoke.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from time import perf_counter
from typing import Any
from uuid import UUID

import httpx
import structlog

from src.domains.shared.consultation_sink import collector_is_active, consultation_collector
from src.domains.shared.consultation_surfaces import record_surface_consultations

logger = structlog.get_logger(__name__)

#: The consultation surface and section the calendar lookup is filed under.
_SURFACE = "meeting"
_CALENDAR_SECTION = "calendar"

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
    *, user_id: UUID, started_at: datetime, stopped_at: datetime
) -> CalendarMatch | None:
    """The user's calendar event overlapping the recording, if any (never raises).

    Opened through the shared calendar door: no session is held while the
    provider answers, and the client is closed on every path (ADR-304). The
    lookup is a CONSULTATION of the person's calendar, filed on the ``meeting``
    surface — ``failed`` when it could not be read, nothing when no calendar is
    connected (nothing was opened).
    """
    from src.domains.connectors.calendar_access import CalendarAccess, open_active_calendar

    started = perf_counter()
    opened = failed = False
    try:
        async with open_active_calendar(user_id) as access:
            if not isinstance(access, CalendarAccess):
                return None
            opened = True
            result = await access.client.list_events(
                time_min=(started_at - _CALENDAR_MARGIN).isoformat(),
                time_max=(stopped_at + _CALENDAR_MARGIN).isoformat(),
                max_results=_MAX_EVENTS,
                calendar_id=access.calendar_id,
                fields=["id", "summary", "start", "end", "attendees", "location"],
            )
            provider = str(getattr(access.connector_type, "value", access.connector_type))
        events = result.get("items", []) or []
    except (TimeoutError, httpx.HTTPError, ValueError, KeyError, AttributeError, OSError) as exc:
        failed = True
        logger.debug("meeting_calendar_match_failed", user_id=str(user_id), error=str(exc))
        return None
    finally:
        if opened:
            record_surface_consultations(
                surface=_SURFACE,
                user_id=user_id,
                opened=[_CALENDAR_SECTION],
                failed=[_CALENDAR_SECTION] if failed else [],
                duration_ms=int((perf_counter() - started) * 1000),
            )

    event = best_overlap(events, started_at, stopped_at)
    if event is None or not event.get("id"):
        return None
    return CalendarMatch(
        event_id=str(event["id"]),
        provider=provider,
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


@asynccontextmanager
async def _consultations_of(run_id: str) -> AsyncIterator[None]:
    """Publish the meeting run's collector, unless a run already collects.

    The register keeps only what a published collector gathers: a background
    job that records without one writes nothing, in silence (ADR-263).
    """
    if collector_is_active():
        yield
        return
    async with consultation_collector(run_id):
        yield


async def enrich_meeting(
    meeting: Any, *, stopped_at: datetime, language: str, run_id: str
) -> tuple[CalendarMatch | None, str | None]:
    """The calendar event and the place name of a recording, under its run's accounting.

    The reverse geocoding is a BILLED Geocoding call on the deployment's key,
    made in a background job where no tracker is ambient — it was dropped in
    silence until 2026-09-20. The meeting's run id is the minutes' own
    (``_notify_ready`` files the synthesis tokens under it), so the euro joins
    the same summary row.

    Neither lookup holds a database session (ADR-304): the job's own
    session must not stay open while a provider answers.

    Args:
        meeting: The ``Meeting`` row.
        stopped_at: When the recording stopped.
        language: The owner's language, for the place name.
        run_id: The meeting run's correlation key.

    Returns:
        The overlapping calendar event (or None) and a location label (or None).
    """
    from src.infrastructure.proactive.tracking import out_of_turn_spend

    async with (
        out_of_turn_spend(run_id, meeting.user_id, "meeting_enrichment"),
        _consultations_of(run_id),
    ):
        calendar = await match_calendar_event(
            user_id=meeting.user_id, started_at=meeting.started_at, stopped_at=stopped_at
        )
        label = meeting.location_label
        if label is None and meeting.location_lat is not None and meeting.location_lon is not None:
            label = await place_label(meeting.location_lat, meeting.location_lon, language=language)
    if label is None and calendar is not None and calendar.location:
        label = calendar.location
    return calendar, label
