"""Routes of the « Tools » calendar screen (ADR-369).

Mounted under ``/workbench`` (the capability guard is the parent router's).
Every id travels in the query string or the body, bounded and checked
(``ids``); reads and writes are counted in two windows. A window is read in the
account's zone; what the page writes is a wall time and its zone, never an
offset.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from src.core.session_dependencies import get_current_active_session_for_stream
from src.core.time_utils import resolve_user_timezone
from src.domains.users.models import User
from src.domains.workbench import calendar_management, calendar_service
from src.domains.workbench.ids import ProviderId
from src.domains.workbench.rate_limits import rate_limit_read, rate_limit_write
from src.domains.workbench.schemas.calendar import (
    CalendarInfo,
    CalendarList,
    CalendarRename,
    EventChange,
    EventDetail,
    EventInvitationAnswer,
    EventMove,
    EventScope,
    EventSearch,
    EventSearchQuery,
    EventsWindow,
    EventWindowQuery,
    NewCalendar,
    NewEvent,
)

router = APIRouter(prefix="/calendar")

_Account = Annotated[User, Depends(get_current_active_session_for_stream)]
_CalendarId = Annotated[ProviderId, Query(description="The event's calendar.")]
_EventId = Annotated[ProviderId, Query(description="The event — an occurrence's own id.")]


@router.get(
    "/calendars",
    response_model=CalendarList,
    summary="The account's calendars",
    dependencies=[Depends(rate_limit_read)],
)
async def get_calendars(user: _Account) -> CalendarList:
    """List the calendars of the signed-in account."""
    return await calendar_service.list_calendars(user.id)


@router.get(
    "/events",
    response_model=EventsWindow,
    summary="The events of some calendars over some of the account's days",
    dependencies=[Depends(rate_limit_read)],
)
async def get_events(query: Annotated[EventWindowQuery, Query()], user: _Account) -> EventsWindow:
    """Read a window, each calendar answered on its own."""
    return await calendar_service.read_window(user.id, resolve_user_timezone(user), query)


@router.get(
    "/event",
    response_model=EventDetail,
    summary="One event, whole",
    dependencies=[Depends(rate_limit_read)],
)
async def get_event(calendar_id: _CalendarId, event_id: _EventId, user: _Account) -> EventDetail:
    """Read one event."""
    return await calendar_service.read_event(user.id, calendar_id, event_id)


@router.get(
    "/search",
    response_model=EventSearch,
    summary="Words looked for in the calendars asked, around today",
    dependencies=[Depends(rate_limit_read)],
)
async def get_search(query: Annotated[EventSearchQuery, Query()], user: _Account) -> EventSearch:
    """Search the calendars."""
    return await calendar_service.search_events(user.id, resolve_user_timezone(user), query)


@router.post(
    "/events",
    response_model=EventDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create an event (the provider's own idempotency: once per form)",
    dependencies=[Depends(rate_limit_write)],
)
async def post_event(request: NewEvent, user: _Account) -> EventDetail:
    """Create an event."""
    return await calendar_service.create_event(user.id, request)


@router.patch(
    "/events",
    response_model=EventDetail,
    summary="Change one event — an occurrence alone",
    dependencies=[Depends(rate_limit_write)],
)
async def patch_event(request: EventChange, user: _Account) -> EventDetail:
    """Change an event."""
    return await calendar_service.update_event(user.id, request)


@router.post(
    "/events/move",
    response_model=EventDetail,
    summary="Move an event to another calendar",
    dependencies=[Depends(rate_limit_write)],
)
async def post_move(request: EventMove, user: _Account) -> EventDetail:
    """Move an event: the id it answers under may change."""
    return await calendar_management.move_event(user.id, request)


@router.post(
    "/calendars",
    response_model=CalendarInfo,
    status_code=status.HTTP_201_CREATED,
    summary="Create a calendar, once per submission",
    dependencies=[Depends(rate_limit_write)],
)
async def post_calendar(request: NewCalendar, user: _Account) -> CalendarInfo:
    """Create a calendar of the person's own."""
    return await calendar_management.create_calendar(user.id, resolve_user_timezone(user), request)


@router.patch(
    "/calendars",
    response_model=CalendarInfo,
    summary="Rename a calendar of the person's own",
    dependencies=[Depends(rate_limit_write)],
)
async def patch_calendar(request: CalendarRename, user: _Account) -> CalendarInfo:
    """Rename a calendar."""
    return await calendar_management.rename_calendar(user.id, request)


@router.delete(
    "/calendars",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a calendar of the person's own, and all it holds",
    dependencies=[Depends(rate_limit_write)],
)
async def delete_calendar(calendar_id: _CalendarId, user: _Account) -> Response:
    """Delete a calendar."""
    await calendar_management.delete_calendar(user.id, calendar_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/events/answer",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Answer an invitation, the organiser told",
    dependencies=[Depends(rate_limit_write)],
)
async def post_answer(request: EventInvitationAnswer, user: _Account) -> Response:
    """Answer an invitation."""
    await calendar_service.answer_event(user.id, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/events",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete one event — an occurrence alone unless the whole series is asked for",
    dependencies=[Depends(rate_limit_write)],
)
async def delete_event(
    calendar_id: _CalendarId,
    event_id: _EventId,
    user: _Account,
    notify: Annotated[
        bool | None,
        Query(description="Tell the attendees (where the provider lets the page choose)."),
    ] = None,
    scope: Annotated[EventScope, Query(description="This occurrence, or its series.")] = (
        "occurrence"
    ),
) -> Response:
    """Delete an event."""
    await calendar_service.delete_event(
        user.id, calendar_id=calendar_id, event_id=event_id, notify=notify, scope=scope
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
