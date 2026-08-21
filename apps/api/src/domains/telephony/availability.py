"""Availability pre-fetch for agentic calls (spec D-5).

Builds a compact free/busy summary from the user's active calendar, projecting
events to busy time ranges ONLY — never titles, attendees, or locations. This is
minimization *by capability*, not by prompt: the projection reads solely the
``start``/``end`` of each event (and asks the provider for just those fields), so
meeting details are never even fetched. The summary is injected as the
``{{availability_summary}}`` dynamic variable so the agent can answer availability
questions on the call without ever seeing what the user is actually doing.

Since lot B (2026-08) the Google client exposes ``query_freebusy``: when the
resolved client offers it, busy ranges come from the freeBusy endpoint (even
less data than the projection). Other providers keep the ``list_events``
start/end projection.

The pre-fetch is best-effort: any resolution/HTTP failure (or no calendar
connector) yields the localized "unavailable" line and NEVER raises — a missing
calendar must not block placing the call.

The structural phrases (header / all-free / unavailable) live in
``core.i18n_telephony`` (all 6 languages).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx
import structlog

from src.core.i18n_telephony import get_availability_phrases
from src.core.time_utils import format_datetime_for_display

if TYPE_CHECKING:
    from src.domains.connectors.models import ConnectorType
    from src.domains.connectors.service import ConnectorService

logger = structlog.get_logger(__name__)

# Hard safety cap on the events pulled for the projection (NOT a business knob):
# the pre-fetch window itself is bounded upstream by telephony_prefetch_window_days.
_MAX_EVENTS = 100


def _busy_line(event: dict[str, Any], user_timezone: str, user_language: str) -> str | None:
    """Project one calendar event to a localized busy range, or ``None``.

    Reads ONLY ``start``/``end`` (Google-shaped: ``dateTime`` for timed events,
    ``date`` for all-day). Titles, attendees and locations are never touched.
    All-day blocks (``date`` only) render as a date without a spurious time.
    """
    start = event.get("start") or {}
    end = event.get("end") or {}
    start_raw = start.get("dateTime") or start.get("date")
    if not start_raw:
        return None
    end_raw = end.get("dateTime") or end.get("date") or ""

    start_fmt = format_datetime_for_display(
        start_raw, user_timezone, user_language, include_time="T" in start_raw
    )
    if not end_raw:
        return f"- {start_fmt}"
    end_fmt = format_datetime_for_display(
        end_raw, user_timezone, user_language, include_time="T" in end_raw
    )
    return f"- {start_fmt} → {end_fmt}"


def summarize_busy_periods(
    events: list[dict[str, Any]], user_timezone: str, user_language: str
) -> str:
    """Project a list of calendar events to a compact free/busy summary.

    This is the leak-critical core: it emits busy time ranges only, never any
    event detail. Pure and side-effect-free so the minimization guarantee is
    unit-testable in isolation.

    Args:
        events: Raw calendar events (Google-shaped ``start``/``end`` dicts).
        user_timezone: IANA timezone the ranges are rendered in.
        user_language: Language for the structural phrases and date formatting.

    Returns:
        A localized summary: a header plus one ``- start → end`` line per busy
        block, or the "all free" line when there are no busy blocks.
    """
    phrases = get_availability_phrases(user_language)
    lines = [
        line
        for event in events
        if (line := _busy_line(event, user_timezone, user_language)) is not None
    ]
    if not lines:
        return phrases["all_free"]
    return phrases["header"] + "\n" + "\n".join(lines)


async def _resolve_calendar_id(
    user_id: UUID,
    resolved_type: ConnectorType,
    client: Any,
    connector_service: ConnectorService,
) -> str:
    """Resolve the user's preferred default calendar id (falls back to primary).

    Delegates to the shared owner-default resolver so availability reflects the
    user's real calendar (a non-primary default would otherwise read empty).
    """
    from src.domains.connectors.preferences.owner_defaults import resolve_owner_calendar_id

    return await resolve_owner_calendar_id(
        db=connector_service.db,
        client=client,
        owner_id=user_id,
        connector_type=resolved_type,
    )


async def build_availability_summary(
    user_id: UUID,
    window_start: datetime,
    window_end: datetime,
    connector_service: ConnectorService,
    user_timezone: str,
    user_language: str = "en",
) -> str:
    """Build the free/busy summary injected as the ``{{availability_summary}}`` var.

    Resolves the user's active calendar connector, pulls events over
    ``[window_start, window_end]`` requesting only ``start``/``end``, and projects
    them to a compact busy summary. Best-effort: returns the localized
    "unavailable" line on any failure and never raises.

    Args:
        user_id: Owner of the calendar.
        window_start: Inclusive lower bound of the pre-fetch window (UTC-aware).
        window_end: Exclusive upper bound of the pre-fetch window (UTC-aware).
        connector_service: Service used to resolve the active calendar + creds.
        user_timezone: IANA timezone the busy ranges are rendered in.
        user_language: Language for phrases + date formatting (app code, e.g.
            ``"fr"``, ``"zh-CN"``).

    Returns:
        The localized free/busy summary string.
    """
    phrases = get_availability_phrases(user_language)
    try:
        from src.domains.connectors.clients.registry import ClientRegistry
        from src.domains.connectors.provider_resolver import resolve_active_connector

        resolved_type = await resolve_active_connector(user_id, "calendar", connector_service)
        if resolved_type is None:
            return phrases["unavailable"]

        credentials = (
            await connector_service.get_apple_credentials(user_id, resolved_type)
            if resolved_type.is_apple
            else await connector_service.get_connector_credentials(user_id, resolved_type)
        )
        if not credentials:
            return phrases["unavailable"]

        client_class = ClientRegistry.get_client_class(resolved_type)
        if client_class is None:
            return phrases["unavailable"]
        client = client_class(user_id, credentials, connector_service)

        calendar_id = await _resolve_calendar_id(user_id, resolved_type, client, connector_service)
        if hasattr(client, "query_freebusy"):
            # Lot B (2026-08): the freeBusy endpoint returns busy ranges only —
            # even less data than the start/end projection, so it wins when
            # the provider offers it. Projected to the Google event shape so
            # summarize_busy_periods stays the single rendering path.
            freebusy = await client.query_freebusy(
                time_min=window_start.isoformat(),
                time_max=window_end.isoformat(),
                calendar_ids=[calendar_id],
            )
            events = [
                {"start": {"dateTime": block.get("start")}, "end": {"dateTime": block.get("end")}}
                for calendar in (freebusy.get("calendars") or {}).values()
                for block in calendar.get("busy", [])
            ]
        else:
            result = await client.list_events(
                time_min=window_start.isoformat(),
                time_max=window_end.isoformat(),
                max_results=_MAX_EVENTS,
                calendar_id=calendar_id,
                # Minimization by capability: never fetch titles/attendees/locations.
                fields=["start", "end"],
            )
            events = result.get("items", []) or []
    except (TimeoutError, httpx.HTTPError, ValueError, KeyError, AttributeError) as exc:
        logger.warning(
            "telephony_availability_prefetch_failed", user_id=str(user_id), error=str(exc)
        )
        return phrases["unavailable"]

    return summarize_busy_periods(events, user_timezone, user_language)
