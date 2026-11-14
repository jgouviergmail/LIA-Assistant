"""A route that STREAMS authenticates on no ``yield`` session (review 2026-09-20).

A ``yield`` dependency lives as long as the response; for a Server-Sent
Events stream, that is the life of the tab. ``get_current_session`` reads the
account on the request's ``Depends(get_db)`` session, whose one SELECT begins
a transaction — measured on dev: every open ``/notifications/stream`` pinned a
PostgreSQL backend in ``idle in transaction`` for as long as it stayed open
(14 minutes at the reading), one per tab, on a pool of five plus fifteen per
worker (ADR-283). The stream routes now authenticate through
``get_current_active_session_for_stream``, which opens and closes its own
session; this guard walks the application's routes and refuses any SSE
endpoint whose dependency tree still reaches a session-yielding door.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi import Depends
from fastapi.dependencies.models import Dependant
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute, RouteContext

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session_for_stream
from src.core.sse_response import EventStreamResponse
from src.infrastructure.database.session import get_db_session
from src.main import app
from tests._routes import served_routes

pytestmark = pytest.mark.unit

#: The doors that yield a request-scoped session.
SESSION_DOORS: tuple[Callable[..., Any], ...] = (get_db, get_db_session)
#: What an endpoint's source says when it streams events to a browser.
SSE_MEDIA_TYPE = "text/event-stream"


def _calls(dependant: Dependant) -> Iterator[Callable[..., Any]]:
    """Every callable of a dependency tree, depth first."""
    for dependency in dependant.dependencies:
        if dependency.call is not None:
            yield dependency.call
        yield from _calls(dependency)


def _sse_routes() -> list[RouteContext]:
    routes = [
        route
        for route in served_routes(app)
        if isinstance(route.original_route, APIRoute)
        and (
            _declares_stream(route.original_route)
            or SSE_MEDIA_TYPE in inspect.getsource(route.endpoint)
        )
    ]
    assert routes, "no SSE route found: the guard's criterion no longer matches the code"
    return routes


def _declares_stream(route: APIRoute) -> bool:
    """Response metadata still identifies a stream constructed by a shared helper."""
    response_class = route.response_class
    return (
        isinstance(response_class, type)
        and issubclass(response_class, StreamingResponse)
        and response_class.media_type == SSE_MEDIA_TYPE
    )


def test_a_helper_built_stream_with_a_session_is_still_detected() -> None:
    """A deliberately bad endpoint proves the detector follows metadata and dependencies."""

    async def bad_endpoint(db: object = Depends(get_db)) -> StreamingResponse:
        raise AssertionError("This fixture must only be inspected")

    route = APIRoute("/bad-stream", bad_endpoint, response_class=EventStreamResponse)
    assert SSE_MEDIA_TYPE not in inspect.getsource(bad_endpoint)
    assert _declares_stream(route)
    assert get_db in set(_calls(route.dependant))
    download = APIRoute("/download", bad_endpoint, response_class=StreamingResponse)
    assert not _declares_stream(download)


def test_the_three_streams_are_found() -> None:
    """Declared transports and inline media types find every known browser stream."""
    paths = {route.path for route in _sse_routes()}
    for suffix in ("/notifications/stream", "/chat/stream", "/runs/{stream_id}/stream"):
        assert any(path.endswith(suffix) for path in paths), (suffix, sorted(paths))


def test_no_sse_route_authenticates_through_a_yield_session() -> None:
    offenders = {
        route.path: sorted(
            getattr(call, "__name__", repr(call))
            for call in _calls(route.dependant)
            if call in SESSION_DOORS
        )
        for route in _sse_routes()
        if any(call in SESSION_DOORS for call in _calls(route.dependant))
    }
    assert not offenders, (
        "an SSE route holds a request session for the life of the stream — authenticate "
        f"it through get_current_active_session_for_stream instead: {offenders}"
    )


def test_every_sse_route_authenticates_through_the_stream_door() -> None:
    """The positive half: a stream that authenticates at all does it through the stream door."""
    for route in _sse_routes():
        calls = list(_calls(route.dependant))
        assert get_current_active_session_for_stream in calls, route.path
