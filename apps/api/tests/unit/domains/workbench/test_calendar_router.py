"""The calendar routes at the door (ADR-369, Task 5.1).

Each route reaches its service for the signed-in account under its window —
reads apart from writes —, the window read in the account's zone. An id of the
wrong shape, or a window past the published days, asks nothing of anyone; an
all-day event is created through the route as DAYS.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from src.core.exceptions import BaseAPIException
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.workbench import calendar_management, calendar_service
from src.domains.workbench import router as router_module
from src.domains.workbench.schemas.calendar import (
    CalendarInfo,
    CalendarList,
    EventDetail,
    EventSearch,
    EventsWindow,
)

pytestmark = pytest.mark.unit

_KEY = "11111111-1111-4111-8111-111111111111"
_DETAIL = EventDetail(
    id="e1",
    calendar_id="primary",
    summary="Congé",
    all_day=True,
    start="2026-11-02",
    end="2026-11-05",
    location=None,
    recurring=False,
    conference_url=None,
    description=None,
    attendees=[],
    organizer=None,
    link=None,
    reminder_minutes=None,
    busy=True,
    private=False,
    zone=None,
    my_response=None,
)
_SERVICES: dict[str, Any] = {
    "list_calendars": CalendarList(calendars=[]),
    "read_window": EventsWindow(calendars=[]),
    "read_event": _DETAIL,
    "answer_event": None,
    "search_events": EventSearch(events=[], truncated=False, failed=[]),
    "create_event": _DETAIL,
    "update_event": _DETAIL,
    "delete_event": None,
}
_CALENDAR = CalendarInfo(
    id="c1",
    name="Trips",
    color=None,
    primary=False,
    default=False,
    writable=True,
    manageable=True,
)
_ACTS: dict[str, Any] = {
    "move_event": _DETAIL,
    "create_calendar": _CALENDAR,
    "rename_calendar": _CALENDAR,
    "delete_calendar": None,
}


async def _handler(_: Any, exc: BaseAPIException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@pytest.fixture
async def http(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[AsyncClient, Any]]:
    monkeypatch.setattr(
        "src.domains.feature_switches.guard.is_capability_enabled", AsyncMock(return_value=True)
    )
    limiter = MagicMock(acquire=AsyncMock(return_value=True))
    monkeypatch.setattr(
        "src.domains.auth.dependencies.get_rate_limiter", AsyncMock(return_value=limiter)
    )
    app = FastAPI()
    app.include_router(router_module.router)
    app.add_exception_handler(BaseAPIException, _handler)  # type: ignore[arg-type]
    user = SimpleNamespace(id=uuid4(), timezone="Europe/Paris")
    app.dependency_overrides[get_current_active_session_for_stream] = lambda: user
    services = {name: AsyncMock(return_value=value) for name, value in _SERVICES.items()}
    acts = {name: AsyncMock(return_value=value) for name, value in _ACTS.items()}
    with (
        patch.multiple(calendar_service, **services),
        patch.multiple(calendar_management, **acts),
    ):
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            yield client, SimpleNamespace(limiter=limiter, user=user, **services, **acts)


_NEW_ALL_DAY = {
    "calendar_id": "primary",
    "summary": "Congé",
    "start": "2026-11-02",
    "end": "2026-11-05",
    "all_day": True,
    "idempotency_key": _KEY,
}
_ROUTES = [
    ("GET", "/workbench/calendar/calendars", None, "list_calendars", 200, "workbench_read"),
    (
        "POST",
        "/workbench/calendar/events/move",
        {"calendar_id": "a", "event_id": "e1", "destination_id": "b"},
        "move_event",
        200,
        "workbench_write",
    ),
    (
        "POST",
        "/workbench/calendar/calendars",
        {"name": "Trips", "idempotency_key": _KEY},
        "create_calendar",
        201,
        "workbench_write",
    ),
    (
        "PATCH",
        "/workbench/calendar/calendars",
        {"calendar_id": "c1", "name": "Sport"},
        "rename_calendar",
        200,
        "workbench_write",
    ),
    (
        "DELETE",
        "/workbench/calendar/calendars?calendar_id=c1",
        None,
        "delete_calendar",
        204,
        "workbench_write",
    ),
    (
        "GET",
        "/workbench/calendar/events?calendar_ids=primary&calendar_ids=c2&start=2026-11-02&end=2026-11-08",
        None,
        "read_window",
        200,
        "workbench_read",
    ),
    (
        "GET",
        "/workbench/calendar/event?calendar_id=primary&event_id=e1",
        None,
        "read_event",
        200,
        "workbench_read",
    ),
    (
        "GET",
        "/workbench/calendar/search?q=budget&calendar_ids=primary",
        None,
        "search_events",
        200,
        "workbench_read",
    ),
    ("POST", "/workbench/calendar/events", _NEW_ALL_DAY, "create_event", 201, "workbench_write"),
    (
        "POST",
        "/workbench/calendar/events/answer",
        {"calendar_id": "c1", "event_id": "e1", "response": "accepted"},
        "answer_event",
        204,
        "workbench_write",
    ),
    (
        "PATCH",
        "/workbench/calendar/events",
        {"calendar_id": "primary", "event_id": "e1", "summary": "x", "notify": False},
        "update_event",
        200,
        "workbench_write",
    ),
    (
        "DELETE",
        "/workbench/calendar/events?calendar_id=primary&event_id=e1&notify=false",
        None,
        "delete_event",
        204,
        "workbench_write",
    ),
]


@pytest.mark.parametrize(("method", "url", "body", "service", "status", "window"), _ROUTES)
async def test_each_route_reaches_its_service_under_its_window(
    http: Any,
    method: str,
    url: str,
    body: dict[str, Any] | None,
    service: str,
    status: int,
    window: str,
) -> None:
    client, seams = http

    response = await client.request(method, url, json=body)

    assert response.status_code == status, response.text
    called = getattr(seams, service)
    called.assert_awaited_once()
    assert called.await_args.args[0] == seams.user.id
    keys = [call.kwargs["key"] for call in seams.limiter.acquire.await_args_list]
    assert [key.split(":")[1] for key in keys] == [window]


async def test_a_calendar_is_created_in_the_account_s_zone(http: Any) -> None:
    client, seams = http

    await client.post(
        "/workbench/calendar/calendars", json={"name": "Trips", "idempotency_key": _KEY}
    )

    assert seams.create_calendar.await_args.args[1] == ZoneInfo("Europe/Paris")


async def test_an_event_does_not_move_onto_its_own_calendar(http: Any) -> None:
    client, seams = http

    response = await client.post(
        "/workbench/calendar/events/move",
        json={"calendar_id": "a", "event_id": "e1", "destination_id": "a"},
    )

    assert response.status_code == 422
    seams.move_event.assert_not_awaited()


async def test_a_window_is_read_in_the_account_s_zone_for_every_calendar(http: Any) -> None:
    client, seams = http

    await client.get(
        "/workbench/calendar/events",
        params=[
            ("calendar_ids", "primary"),
            ("calendar_ids", "c2"),
            ("start", "2026-11-02"),
            ("end", "2026-11-08"),
        ],
    )

    _user_id, zone, query = seams.read_window.await_args.args
    assert zone == ZoneInfo("Europe/Paris")
    assert query.calendar_ids == ["primary", "c2"]


async def test_an_all_day_event_is_created_through_the_route_as_days(http: Any) -> None:
    client, seams = http

    response = await client.post("/workbench/calendar/events", json=_NEW_ALL_DAY)

    request = seams.create_event.await_args.args[1]
    assert (request.all_day, request.start, request.end) == (True, "2026-11-02", "2026-11-05")
    assert response.json()["all_day"] is True


async def test_a_deletion_carries_the_attendees_choice(http: Any) -> None:
    client, seams = http

    await client.delete(
        "/workbench/calendar/events",
        params={"calendar_id": "primary", "event_id": "e1", "notify": "false"},
    )

    assert seams.delete_event.await_args.kwargs == {
        "calendar_id": "primary",
        "event_id": "e1",
        "notify": False,
        "scope": "occurrence",
    }


@pytest.mark.parametrize(
    "url",
    [
        "/workbench/calendar/event?calendar_id=primary&event_id=a%20b",
        "/workbench/calendar/events?calendar_ids=primary&start=2026-11-01&end=2026-12-31",
        "/workbench/calendar/events?start=2026-11-02&end=2026-11-02",
    ],
)
async def test_an_odd_id_or_window_asks_nothing(http: Any, url: str) -> None:
    client, seams = http

    response = await client.get(url)

    assert response.status_code == 422
    seams.read_event.assert_not_awaited()
    seams.read_window.assert_not_awaited()
