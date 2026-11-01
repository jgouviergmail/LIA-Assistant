"""The lights routes at the door (ADR-369, Task 9.1).

The bridge is read under the read window; a lamp, a room or a scene is set
under the write window and answers nothing (the screen keeps what it drew); a
value off the contract — a colour that is not #rrggbb, a brightness past 100,
an id of the wrong shape — is refused before the bridge is asked.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from src.core.exceptions import BaseAPIException
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.workbench import lights_service
from src.domains.workbench import router as router_module
from src.domains.workbench.schemas.lights import LightsView

pytestmark = pytest.mark.unit

_LAMP = "11111111-1111-4111-8111-111111111111"


async def _handler(_: Any, exc: BaseAPIException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers
    )


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
    user = SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_current_active_session_for_stream] = lambda: user
    services = {
        "read_lights": AsyncMock(return_value=LightsView(rooms=[], lights=[], scenes=[])),
        "change_light": AsyncMock(return_value=None),
        "change_room": AsyncMock(return_value=None),
        "recall_scene": AsyncMock(return_value=None),
    }
    with patch.multiple(lights_service, **services):
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            yield client, SimpleNamespace(limiter=limiter, user=user, **services)


@pytest.mark.parametrize(
    ("method", "url", "body", "service", "status", "window"),
    [
        ("GET", "/workbench/lights", None, "read_lights", 200, "workbench_read"),
        (
            "POST",
            "/workbench/lights/light",
            {"light_id": _LAMP, "color_hex": "#ff8800"},
            "change_light",
            204,
            "workbench_write",
        ),
        (
            "POST",
            "/workbench/lights/room",
            {"room_id": _LAMP, "on": False},
            "change_room",
            204,
            "workbench_write",
        ),
        (
            "POST",
            "/workbench/lights/scene",
            {"scene_id": _LAMP},
            "recall_scene",
            204,
            "workbench_write",
        ),
    ],
)
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
    assert f"auth:{window}:user:" in seams.limiter.acquire.await_args.kwargs["key"]


@pytest.mark.parametrize(
    "body",
    [
        {"light_id": _LAMP, "color_hex": "orange"},
        {"light_id": _LAMP, "brightness": 101},
        {"light_id": "a b", "on": True},
        {"light_id": _LAMP, "on": True, "extra": 1},
    ],
)
async def test_a_value_off_the_contract_asks_nothing(http: Any, body: dict[str, Any]) -> None:
    client, seams = http
    response = await client.post("/workbench/lights/light", json=body)
    assert response.status_code == 422
    seams.change_light.assert_not_awaited()
