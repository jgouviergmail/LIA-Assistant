"""``GET /workbench`` at the door: guard, authentication, rate window, shape (ADR-369)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.exceptions import BaseAPIException
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.workbench import router as router_module
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.schemas.common import (
    ToolAvailability,
    WorkbenchAvailability,
    WorkbenchLimits,
)

pytestmark = pytest.mark.unit

_PAYLOAD = WorkbenchAvailability(
    tools=[
        ToolAvailability(tool=tool, state="not_connected", provider=None, features=[], bounds={})
        for tool in WorkbenchTool
    ],
    limits=WorkbenchLimits(
        page_size=25,
        bulk_max_items=50,
        download_max_bytes=1,
        upload_max_bytes=1,
        calendar_window_max_events=500,
        send_undo_seconds=5,
        draft_autosave_seconds=15,
        search_max_chars=500,
        assist_text_max_chars=8000,
        assist_instruction_max_chars=500,
    ),
)


async def _exception_handler(_: Any, exc: BaseAPIException) -> Any:
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers
    )


@pytest.fixture
async def http(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[AsyncClient, Any]]:
    enabled = AsyncMock(return_value=True)
    monkeypatch.setattr("src.domains.feature_switches.guard.is_capability_enabled", enabled)
    limiter = MagicMock(acquire=AsyncMock(return_value=True))
    monkeypatch.setattr(
        "src.domains.auth.dependencies.get_rate_limiter", AsyncMock(return_value=limiter)
    )
    app = FastAPI()
    app.include_router(router_module.router)
    app.add_exception_handler(BaseAPIException, _exception_handler)  # type: ignore[arg-type]
    user = SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_current_active_session_for_stream] = lambda: user
    with patch.object(router_module, "read_availability", AsyncMock(return_value=_PAYLOAD)) as read:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            yield client, SimpleNamespace(enabled=enabled, limiter=limiter, read=read, user=user)


async def test_the_rail_is_served_for_the_signed_in_account(http: Any) -> None:
    client, seams = http
    response = await client.get("/workbench")
    assert response.status_code == 200
    body = response.json()
    assert [tool["tool"] for tool in body["tools"]] == [t.value for t in WorkbenchTool]
    assert body["limits"]["page_size"] == 25
    seams.read.assert_awaited_once_with(seams.user.id)


async def test_a_switched_off_section_refuses(http: Any) -> None:
    client, seams = http
    seams.enabled.return_value = False
    response = await client.get("/workbench")
    assert response.status_code == 403
    seams.read.assert_not_awaited()


async def test_the_read_window_applies(http: Any) -> None:
    client, seams = http
    seams.limiter.acquire.return_value = False
    response = await client.get("/workbench")
    assert response.status_code == 429
    assert response.headers["retry-after"]
    seams.read.assert_not_awaited()
