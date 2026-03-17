"""
Apple iCloud Calendar client (CalDAV).

Implements the same interface as GoogleCalendarClient for transparent
provider switching via functional_category in ConnectorTool.

Uses caldav.aio (async native) — no asyncio.to_thread() needed.

IMPORTANT: event_by_uid() is broken on iCloud.
Always use calendar.search() + client-side UID filter.

Created: 2026-03-10
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog

from src.core.config import settings
from src.domains.connectors.clients.base_apple_client import BaseAppleClient
from src.domains.connectors.clients.normalizers.calendar_normalizer import (
    normalize_calendar,
    normalize_vevent,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import AppleCredentials

logger = structlog.get_logger(__name__)


class AppleCalendarClient(BaseAppleClient):
    """
    Apple iCloud Calendar client using CalDAV.

    Interface matches GoogleCalendarClient for transparent provider switching.
    """

    connector_type = ConnectorType.APPLE_CALENDAR

    def __init__(
        self,
        user_id: UUID,
        credentials: AppleCredentials,
        connector_service: Any,
    ) -> None:
        super().__init__(user_id, credentials, connector_service)
        self._dav_client: Any | None = None
        self._principal: Any | None = None

    # =========================================================================
    # CalDAV CONNECTION
    # =========================================================================

    async def _get_principal(self) -> Any:
        """Get or create CalDAV principal (lazy init with discovery)."""
        if self._principal is None:
            try:
                from caldav.aio import get_async_davclient

                self._dav_client = await get_async_davclient(
                    url=settings.apple_caldav_url,
                    username=self.credentials.apple_id,
                    password=self.credentials.app_password,
                )
                self._principal = await self._dav_client.get_principal()
            except Exception as e:
                self._check_http_auth_error(getattr(getattr(e, "response", None), "status_code", 0))
                raise
        return self._principal

    async def _get_calendar(self, calendar_id: str = "primary") -> Any:
        """Get a specific calendar by ID or the default (primary)."""
        principal = await self._get_principal()
        calendars = await principal.get_calendars()

        logger.debug(
            "caldav_calendars_found",
            count=len(calendars),
            calendars=[{"name": getattr(c, "name", "?"), "url": str(c.url)} for c in calendars],
        )

        if not calendars:
            raise ValueError("No calendars found on this iCloud account")

        if calendar_id == "primary":
            return calendars[0]  # First calendar is default

        # Match by URL or display name
        for cal in calendars:
            cal_url = str(cal.url)
            cal_name = getattr(cal, "name", "")
            if calendar_id in (cal_url, cal_name):
                return cal

        raise ValueError(f"Calendar '{calendar_id}' not found")

    # =========================================================================
    # PUBLIC INTERFACE (matches GoogleCalendarClient exactly)
    # =========================================================================

    async def list_calendars(
        self, max_results: int = 100, show_hidden: bool = False
    ) -> dict[str, Any]:
        """List all calendars."""
        return await self._execute_with_retry(
            "list_calendars",
            self._list_calendars_impl,
            max_results,
            show_hidden,
        )

    async def list_events(
        self,
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 10,
        calendar_id: str = "primary",
        query: str | None = None,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """List events in a calendar."""
        return await self._execute_with_retry(
            "list_events",
            self._list_events_impl,
            time_min,
            time_max,
            max_results,
            calendar_id,
            query,
            fields,
        )

    async def get_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get a single event by UID."""
        return await self._execute_with_retry(
            "get_event",
            self._get_event_impl,
            event_id,
            calendar_id,
            fields,
        )

    async def create_event(
        self,
        summary: str,
        start_datetime: str,
        end_datetime: str,
        timezone: str | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """Create a new event."""
        return await self._execute_with_retry(
            "create_event",
            self._create_event_impl,
            summary,
            start_datetime,
            end_datetime,
            timezone,
            description,
            location,
            attendees,
            calendar_id,
        )

    async def update_event(
        self,
        event_id: str,
        summary: str | None = None,
        start_datetime: str | None = None,
        end_datetime: str | None = None,
        timezone: str | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """Update an existing event (full PUT, no PATCH on iCloud)."""
        return await self._execute_with_retry(
            "update_event",
            self._update_event_impl,
            event_id,
            summary,
            start_datetime,
            end_datetime,
            timezone,
            description,
            location,
            attendees,
            calendar_id,
        )

    async def delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        send_updates: str = "all",
    ) -> dict[str, Any]:
        """Delete an event."""
        return await self._execute_with_retry(
            "delete_event",
            self._delete_event_impl,
            event_id,
            calendar_id,
            send_updates,
        )

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    async def _find_event_by_uid(self, calendar: Any, event_id: str) -> Any:
        """
        Search for a CalDAV event by UID.

        IMPORTANT: event_by_uid() is broken on iCloud.
        We use search() + client-side UID filtering instead.

        Returns the raw caldav event object or None.
        """
        now = datetime.now(tz=UTC)
        events = await calendar.search(
            start=now - timedelta(days=365),
            end=now + timedelta(days=365),
            event=True,
        )

        for event in events:
            try:
                vevent = event.vobject_instance.vevent
                uid = str(vevent.uid.value) if hasattr(vevent, "uid") else ""
                if uid == event_id:
                    return event
            except Exception:
                continue

        return None

    @staticmethod
    def _apply_timezone(dt: datetime, timezone: str) -> datetime:
        """Apply timezone to a naive datetime. Timezone-aware datetimes are unchanged."""
        if dt.tzinfo is not None:
            return dt
        return dt.replace(tzinfo=ZoneInfo(timezone))

    # =========================================================================
    # IMPLEMENTATION
    # =========================================================================

    async def _list_calendars_impl(self, max_results: int, show_hidden: bool) -> dict[str, Any]:
        """List all CalDAV calendars."""
        principal = await self._get_principal()
        calendars = await principal.get_calendars()

        items = []
        for i, cal in enumerate(calendars[:max_results]):
            normalized = normalize_calendar(cal)
            if i == 0:
                normalized["primary"] = True
            items.append(normalized)

        return {"items": items}

    async def _list_events_impl(
        self,
        time_min: str | None,
        time_max: str | None,
        max_results: int,
        calendar_id: str,
        query: str | None,
        fields: list[str] | None,
    ) -> dict[str, Any]:
        """List events via CalDAV REPORT."""
        calendar = await self._get_calendar(calendar_id)

        # Parse date range
        search_kwargs: dict[str, Any] = {"event": True}
        if time_min:
            search_kwargs["start"] = _parse_iso_datetime(time_min)
        if time_max:
            search_kwargs["end"] = _parse_iso_datetime(time_max)

        # Default range if not specified
        if "start" not in search_kwargs and "end" not in search_kwargs:
            now = datetime.now(tz=UTC)
            search_kwargs["start"] = now - timedelta(days=30)
            search_kwargs["end"] = now + timedelta(days=90)

        logger.debug(
            "caldav_search_params",
            calendar_url=str(calendar.url),
            calendar_name=getattr(calendar, "name", "unknown"),
            search_kwargs={k: str(v) for k, v in search_kwargs.items()},
        )
        events = await calendar.search(**search_kwargs)
        logger.debug(
            "caldav_search_results",
            events_count=len(events) if events else 0,
        )

        items = []
        for event in events:
            try:
                normalized = normalize_vevent(event)

                # Client-side query filtering (CalDAV search doesn't support text search)
                if query:
                    query_lower = query.lower()
                    summary = normalized.get("summary", "").lower()
                    description = normalized.get("description", "").lower()
                    if query_lower not in summary and query_lower not in description:
                        continue

                items.append(normalized)
            except Exception as e:
                logger.warning(
                    "apple_calendar_event_parse_error",
                    error=str(e),
                    event_url=str(getattr(event, "url", "unknown")),
                )

        # Sort by start time (most recent first)
        items.sort(
            key=lambda x: x.get("start", {}).get("dateTime", x.get("start", {}).get("date", "")),
            reverse=False,  # Ascending chronological (matches Google Calendar API)
        )

        return {"items": items[:max_results]}

    async def _get_event_impl(
        self,
        event_id: str,
        calendar_id: str,
        fields: list[str] | None,
    ) -> dict[str, Any]:
        """Get a single event by UID."""
        calendar = await self._get_calendar(calendar_id)
        event = await self._find_event_by_uid(calendar, event_id)

        if event is None:
            raise ValueError(f"Event '{event_id}' not found in calendar")

        return normalize_vevent(event)

    async def _create_event_impl(
        self,
        summary: str,
        start_datetime: str,
        end_datetime: str,
        timezone: str | None,
        description: str | None,
        location: str | None,
        attendees: list[str] | None,
        calendar_id: str,
    ) -> dict[str, Any]:
        """Create a new event via CalDAV."""
        calendar = await self._get_calendar(calendar_id)

        dtstart = _parse_iso_datetime(start_datetime)
        dtend = _parse_iso_datetime(end_datetime)

        # Apply timezone to naive datetimes if specified
        if timezone:
            dtstart = self._apply_timezone(dtstart, timezone)
            dtend = self._apply_timezone(dtend, timezone)

        kwargs: dict[str, Any] = {
            "dtstart": dtstart,
            "dtend": dtend,
            "summary": summary,
        }
        if description:
            kwargs["description"] = description
        if location:
            kwargs["location"] = location

        event = await calendar.save_event(**kwargs)

        # Add attendees if specified (modify VEVENT post-creation)
        if attendees and event.vobject_instance:
            vevent = event.vobject_instance.vevent
            for email in attendees:
                att = vevent.add("attendee")
                att.value = f"mailto:{email}"
            await event.save()

        return normalize_vevent(event)

    async def _update_event_impl(
        self,
        event_id: str,
        summary: str | None,
        start_datetime: str | None,
        end_datetime: str | None,
        timezone: str | None,
        description: str | None,
        location: str | None,
        attendees: list[str] | None,
        calendar_id: str,
    ) -> dict[str, Any]:
        """
        Update an existing event (full PUT, no PATCH on iCloud).

        Gets the existing event, modifies fields, then saves.
        """
        calendar = await self._get_calendar(calendar_id)
        target_event = await self._find_event_by_uid(calendar, event_id)

        if target_event is None:
            raise ValueError(f"Event '{event_id}' not found for update")

        vevent = target_event.vobject_instance.vevent

        # Update fields (only non-None values)
        if summary is not None:
            vevent.summary.value = summary

        if start_datetime is not None:
            dt = _parse_iso_datetime(start_datetime)
            if timezone:
                dt = self._apply_timezone(dt, timezone)
            vevent.dtstart.value = dt

        if end_datetime is not None:
            dt = _parse_iso_datetime(end_datetime)
            if timezone:
                dt = self._apply_timezone(dt, timezone)
            vevent.dtend.value = dt

        if description is not None:
            if hasattr(vevent, "description"):
                vevent.description.value = description
            else:
                vevent.add("description").value = description

        if location is not None:
            if hasattr(vevent, "location"):
                vevent.location.value = location
            else:
                vevent.add("location").value = location

        if attendees is not None:
            # Remove existing attendees
            while hasattr(vevent, "attendee"):
                vevent.remove(vevent.attendee)
            # Add new ones
            for email in attendees:
                att = vevent.add("attendee")
                att.value = f"mailto:{email}"

        await target_event.save()
        return normalize_vevent(target_event)

    async def _delete_event_impl(
        self,
        event_id: str,
        calendar_id: str,
        send_updates: str,
    ) -> dict[str, Any]:
        """Delete an event via CalDAV."""
        calendar = await self._get_calendar(calendar_id)
        event = await self._find_event_by_uid(calendar, event_id)

        if event is None:
            raise ValueError(f"Event '{event_id}' not found for deletion")

        await event.delete()
        return {
            "success": True,
            "event_id": event_id,
            "message": f"Event '{event_id}' deleted successfully",
        }

    # =========================================================================
    # CLEANUP
    # =========================================================================

    async def close(self) -> None:
        """Close CalDAV client connection."""
        if self._dav_client:
            try:
                await self._dav_client.close()
            except Exception as e:
                logger.debug("caldav_close_error", error=str(e))
            self._dav_client = None
            self._principal = None


def _parse_iso_datetime(dt_str: str) -> datetime:
    """Parse ISO 8601 datetime string to timezone-aware datetime object."""
    # Normalize trailing Z to +00:00 so strptime %z handles it as UTC
    normalized = dt_str.replace("Z", "+00:00") if dt_str.endswith("Z") else dt_str
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(normalized, fmt)
            # Ensure UTC for naive datetimes (no timezone in input)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            continue
    # Fallback: use dateutil
    from dateutil.parser import parse

    return parse(dt_str)
