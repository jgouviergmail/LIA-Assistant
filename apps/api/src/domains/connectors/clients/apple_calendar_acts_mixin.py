"""What iCloud's calendars do beyond events: moving one, managing calendars (ADR-369, lot 5).

Beside ``apple_calendar_client``, close to its size cap. CalDAV has no move its servers
share: the event's own iCalendar text is written in the destination, whole, under its UID,
then the original removed. A calendar's rename is a ``PROPPATCH`` of its display name, and
its deletion a real ``DELETE``: caldav's default empties a calendar on the servers it does
not trust to delete one, which would leave an empty calendar behind a confirmed deletion.

No test account exists for iCloud: every path here is proven by doubles alone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from src.domains.connectors.clients.calendar_management import (
    EventLeftBehindError,
    EventNotMovableError,
)
from src.domains.connectors.clients.normalizers.calendar_normalizer import (
    normalize_calendar,
    normalize_vevent,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class _AppleCalendarHost(Protocol):
    """What the acts read of the client."""

    _execute_with_retry: Callable[..., Awaitable[Any]]
    _get_calendar: Callable[..., Awaitable[Any]]
    _get_principal: Callable[..., Awaitable[Any]]
    _find_event_by_uid: Callable[..., Awaitable[Any]]


class AppleCalendarActsMixin:
    """Moving an event and managing calendars, over CalDAV."""

    async def move_event(
        self: _AppleCalendarHost, event_id: str, calendar_id: str, destination_id: str
    ) -> dict[str, Any]:
        """Write the event in the destination, then remove the original.

        Sent once: a write whose answer was lost is not repeated, and the original stays.

        Args:
            event_id: The event's UID.
            calendar_id: The calendar it is in.
            destination_id: The calendar it goes to.

        Returns:
            The event as the destination holds it.

        Raises:
            EventNotMovableError: It has guests or is a series: nothing was sent.
            EventLeftBehindError: It was written, and the original could not be removed.
            ValueError: The calendar holds no such event.
        """
        return await self._execute_with_retry(
            "move_event",
            _move_event,
            self,
            event_id,
            calendar_id,
            destination_id,
            max_retries=0,
        )

    async def create_calendar(
        self: _AppleCalendarHost, name: str, timezone: str | None = None
    ) -> dict[str, Any]:
        """Create a calendar of the account's.

        Args:
            name: Its name.
            timezone: Unused: CalDAV events carry their own.

        Returns:
            The calendar, as a listing names it.
        """
        return await self._execute_with_retry(
            "create_calendar", _create_calendar, self, name, max_retries=0
        )

    async def rename_calendar(
        self: _AppleCalendarHost, calendar_id: str, name: str
    ) -> dict[str, Any]:
        """Give a calendar another name.

        Args:
            calendar_id: The calendar.
            name: Its new name.

        Returns:
            The calendar, as a listing names it.
        """
        return await self._execute_with_retry(
            "rename_calendar", _rename_calendar, self, calendar_id, name
        )

    async def delete_calendar(self: _AppleCalendarHost, calendar_id: str) -> None:
        """Delete a calendar and all it holds.

        Args:
            calendar_id: The calendar.
        """
        await self._execute_with_retry(
            "delete_calendar", _delete_calendar, self, calendar_id, max_retries=0
        )


async def _move_event(
    host: _AppleCalendarHost, event_id: str, calendar_id: str, destination_id: str
) -> dict[str, Any]:
    source = await host._get_calendar(calendar_id)
    target = await host._get_calendar(destination_id)
    event = await host._find_event_by_uid(source, event_id)
    if event is None:
        raise ValueError(f"Event '{event_id}' not found")
    vevent = event.vobject_instance.vevent
    if getattr(vevent, "attendee_list", None) or hasattr(vevent, "rrule"):
        raise EventNotMovableError
    # The text as it came: what vobject does not model goes through untouched.
    moved = await target.save_event(ical=event.data)
    try:
        await event.delete()
    except Exception as error:
        raise EventLeftBehindError from error
    return normalize_vevent(moved)


async def _create_calendar(host: _AppleCalendarHost, name: str) -> dict[str, Any]:
    principal = await host._get_principal()
    made = await principal.make_calendar(name=name)
    return normalize_calendar(made, name)


async def _rename_calendar(host: _AppleCalendarHost, calendar_id: str, name: str) -> dict[str, Any]:
    # Local, as the client's own caldav import: an account with no iCloud loads none of it.
    from caldav.elements import dav

    calendar = await host._get_calendar(calendar_id)
    await calendar.set_properties([dav.DisplayName(name)])
    return normalize_calendar(calendar, name)


async def _delete_calendar(host: _AppleCalendarHost, calendar_id: str) -> None:
    calendar = await host._get_calendar(calendar_id)
    await calendar.delete(wipe=False)
