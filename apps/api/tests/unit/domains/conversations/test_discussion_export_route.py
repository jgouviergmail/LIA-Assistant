"""The export route holds nothing while the document streams (ADR-304).

A ``yield`` dependency lives as long as the response. A download of a whole
discussion can last, and ``Depends(get_db)`` would pin a pooled connection — and
whatever its ownership read locked — for all of it. The SSE guard
(``test_streaming_routes_hold_no_session_guard``) reads event streams only: a
streamed DOWNLOAD is invisible to it, so this route carries its own.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.dependencies.models import Dependant

from src.core.dependencies import get_db
from src.core.session_dependencies import (
    get_current_active_session,
    get_current_active_session_for_stream,
)
from src.infrastructure.database.session import get_db_session
from src.main import app
from tests._routes import served_routes

pytestmark = pytest.mark.unit

EXPORT_PATH = "/api/v1/conversations/me/export"


def _calls(dependant: Dependant) -> Iterator[Callable[..., Any]]:
    """Every callable of a dependency tree, depth first."""
    for dependency in dependant.dependencies:
        if dependency.call is not None:
            yield dependency.call
        yield from _calls(dependency)


def _export_calls() -> list[Callable[..., Any]]:
    (route,) = [route for route in served_routes(app) if route.path == EXPORT_PATH]
    return list(_calls(route.dependant))


def test_the_export_reaches_no_request_scoped_session() -> None:
    calls = _export_calls()

    assert get_db not in calls and get_db_session not in calls
    # The request-session door of authentication would bring one back.
    assert get_current_active_session not in calls


def test_the_export_and_its_rate_limit_authenticate_through_the_stream_door() -> None:
    calls = _export_calls()

    # Once for the route, once for its per-account limiter: neither pins a session.
    assert calls.count(get_current_active_session_for_stream) >= 2
