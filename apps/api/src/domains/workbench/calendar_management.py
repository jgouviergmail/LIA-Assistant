"""Moving an event and managing calendars, in the « Tools » section (ADR-369, lot 5).

Beside ``calendar_service``: what is read there is answered in its vocabulary. These are the
person's own acts, by hand: nothing here reaches the assistant (spec of lot 5).

ONE door decides which calendars may be renamed or deleted, whatever a request names: the
listing (``calendar_info``), read before the act. A name a calendar already answers to is
refused here for every provider: iCloud finds a calendar by its name, and two of one name
would answer for each other.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.protocols import (
    CalendarClientProtocol,
    CalendarManagementProtocol,
)
from src.domains.workbench.calendar_service import calendar_info, event_detail
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import (
    ITEM_GONE,
    NAME_TAKEN,
    NOT_SUPPORTED_BY_PROVIDER,
    refuse,
)
from src.domains.workbench.features import PROVIDER_FEATURES, WorkbenchFeature, WorkbenchTool
from src.domains.workbench.idempotency import run_once
from src.domains.workbench.schemas.calendar import (
    CalendarInfo,
    CalendarRename,
    EventDetail,
    EventMove,
    NewCalendar,
)

_TOOL = WorkbenchTool.CALENDAR


async def move_event(user_id: UUID, request: EventMove) -> EventDetail:
    """Move an event to another calendar.

    Args:
        user_id: The account.
        request: The event, its calendar, and the one it goes to.

    Returns:
        The event where it is now, under the id the provider gave it there.
    """
    async with open_tool_client(_TOOL, user_id) as opened:
        _require(opened, WorkbenchFeature.EVENT_MOVE)
        client: CalendarManagementProtocol = opened.client
        async with provider_call(_TOOL, "move_event", act=True):
            raw = await client.move_event(
                request.event_id, request.calendar_id, request.destination_id
            )
    return event_detail(raw, request.destination_id)


async def create_calendar(user_id: UUID, zone: ZoneInfo, request: NewCalendar) -> CalendarInfo:
    """Create a calendar of the person's own, once per submission.

    Args:
        user_id: The account.
        zone: The account's zone, which a provider that keeps one takes for the calendar's.
        request: Its name and the submission's key.

    Returns:
        The calendar.
    """

    async def create() -> CalendarInfo:
        async with open_tool_client(_TOOL, user_id) as opened:
            _require(opened, WorkbenchFeature.CALENDAR_MANAGEMENT)
            client: CalendarManagementProtocol = opened.client
            _refuse_taken(await _listing(opened.client), request.name)
            async with provider_call(_TOOL, "create_calendar", act=True):
                raw = await client.create_calendar(request.name, zone.key)
        return calendar_info(raw, None)

    return await run_once(
        user_id,
        request.idempotency_key,
        create,
        tool=_TOOL.value,
        record=lambda made: {"calendar_id": made.id},
    )


async def rename_calendar(user_id: UUID, request: CalendarRename) -> CalendarInfo:
    """Give a calendar of the person's own another name.

    Args:
        user_id: The account.
        request: The calendar and its new name.

    Returns:
        The calendar.
    """
    async with open_tool_client(_TOOL, user_id) as opened:
        _require(opened, WorkbenchFeature.CALENDAR_MANAGEMENT)
        client: CalendarManagementProtocol = opened.client
        listing = await _listing(opened.client)
        _require_own(listing, request.calendar_id)
        _refuse_taken(listing, request.name, but=request.calendar_id)
        async with provider_call(_TOOL, "rename_calendar", act=True):
            raw = await client.rename_calendar(request.calendar_id, request.name)
    return calendar_info(raw, None)


async def delete_calendar(user_id: UUID, calendar_id: str) -> None:
    """Delete a calendar of the person's own, and all it holds.

    Args:
        user_id: The account.
        calendar_id: The calendar.
    """
    async with open_tool_client(_TOOL, user_id) as opened:
        _require(opened, WorkbenchFeature.CALENDAR_MANAGEMENT)
        client: CalendarManagementProtocol = opened.client
        _require_own(await _listing(opened.client), calendar_id)
        async with provider_call(_TOOL, "delete_calendar", act=True):
            await client.delete_calendar(calendar_id)


def _require(opened: ActiveClient, feature: WorkbenchFeature) -> None:
    """Refuse, unsent, a gesture the active provider does not accept."""
    if feature not in PROVIDER_FEATURES[opened.connector_type]:
        refuse(NOT_SUPPORTED_BY_PROVIDER)


async def _listing(client: CalendarClientProtocol) -> list[Mapping[str, Any]]:
    """The account's calendars as the provider lists them."""
    async with provider_call(_TOOL, "list_calendars", act=False):
        raw = await client.list_calendars()
    return list(raw.get("items") or [])


def _require_own(listing: list[Mapping[str, Any]], calendar_id: str) -> None:
    """Refuse a calendar the listing does not hold, or does not leave to the person."""
    found = next((item for item in listing if item.get("id") == calendar_id), None)
    if found is None:
        refuse(ITEM_GONE)
    if not calendar_info(found, None).manageable:
        refuse(NOT_SUPPORTED_BY_PROVIDER)


def _refuse_taken(listing: list[Mapping[str, Any]], name: str, *, but: str | None = None) -> None:
    """Refuse a name another calendar answers to, whatever its case."""
    wanted = name.casefold()
    for item in listing:
        if item.get("id") != but and calendar_info(item, None).name.casefold() == wanted:
            refuse(NAME_TAKEN)


__all__ = ["create_calendar", "delete_calendar", "move_event", "rename_calendar"]
