"""Guard: every operation the API serves is mounted once.

A router included twice serves each of its operations twice. Nothing fails:
the first copy answers every request, the second is dead weight carrying a
duplicate operation id into the OpenAPI document. Measured 2026-11-13: the
writing style's router (ADR-383) was included twice in ``api/v1/routes.py``,
and no test noticed.

A WebSocket has no method: it is counted under ``WEBSOCKET``.
"""

from __future__ import annotations

from collections import Counter

import pytest
from fastapi import APIRouter

from src.api.v1.routes import api_router
from tests._routes import served_routes


def _served_twice(owner: APIRouter) -> list[str]:
    """The operations ``owner`` serves more than once, as ``METHOD /path``."""
    served = Counter(
        (method, route.path)
        for route in served_routes(owner)
        for method in sorted(route.methods or {"WEBSOCKET"})
    )
    return sorted(f"{method} {path}" for (method, path), count in served.items() if count > 1)


@pytest.mark.unit
def test_the_detector_sees_a_router_included_twice() -> None:
    inner = APIRouter(prefix="/inner")

    @inner.get("/thing")
    async def thing() -> None:
        """A route of the router included twice."""

    @inner.websocket("/socket")
    async def socket() -> None:
        """A WebSocket of the router included twice."""

    outer = APIRouter()
    outer.include_router(inner)
    outer.include_router(inner)

    assert _served_twice(outer) == ["GET /inner/thing", "WEBSOCKET /inner/socket"]


@pytest.mark.unit
def test_the_detector_leaves_one_path_with_two_methods_alone() -> None:
    router = APIRouter()

    @router.get("/thing")
    async def read() -> None:
        """Reads the thing."""

    @router.delete("/thing")
    async def remove() -> None:
        """Removes the thing."""

    assert _served_twice(router) == []


@pytest.mark.unit
def test_every_operation_of_the_api_is_served_once() -> None:
    twice = _served_twice(api_router)

    assert not twice, (
        "an operation is mounted more than once — a router included twice in "
        f"api/v1/routes.py serves every route it holds twice: {twice}"
    )
