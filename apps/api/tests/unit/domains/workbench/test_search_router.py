"""The global search at the door (ADR-369, lot 13)."""

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

from src.core.constants import WORKBENCH_MAIL_QUERY_MAX_CHARS
from src.core.exceptions import BaseAPIException
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.workbench import router as router_module
from src.domains.workbench import search
from src.domains.workbench.schemas.search import GlobalSearch, SearchHit, ToolHits

pytestmark = pytest.mark.unit

FOUND = GlobalSearch(
    results=[
        ToolHits(
            tool="mail",
            hits=[SearchHit(id="m1", title="Budget", subtitle="Ana", mail_folder="system:all")],
            truncated=False,
            inbox_only=False,
        )
    ],
    failed=["files"],
)


async def _handler(_: Any, exc: BaseAPIException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


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
    app.add_exception_handler(BaseAPIException, _handler)  # type: ignore[arg-type]
    user = SimpleNamespace(id=uuid4(), timezone="Europe/Paris")
    app.dependency_overrides[get_current_active_session_for_stream] = lambda: user
    searched = AsyncMock(return_value=FOUND)
    with patch.object(search, "search_everything", searched):
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            yield client, SimpleNamespace(
                enabled=enabled, limiter=limiter, searched=searched, user=user
            )


async def test_the_words_reach_the_search_for_the_signed_in_account(http: Any) -> None:
    client, seams = http

    answer = await client.get("/workbench/search", params={"q": " ana "})

    assert answer.status_code == 200
    assert answer.json()["failed"] == ["files"]
    assert answer.json()["results"][0]["hits"][0]["mail_folder"] == "system:all"
    user_id, zone, words = seams.searched.await_args.args
    assert (user_id, str(zone), words) == (seams.user.id, "Europe/Paris", "ana")


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"q": "   "},
        {"q": "x" * (WORKBENCH_MAIL_QUERY_MAX_CHARS + 1)},
        {"q": "ana\x00"},
        {"q": "ana", "extra": "x"},
    ],
)
async def test_words_that_cannot_be_searched_ask_nothing_of_anyone(
    http: Any, params: dict[str, str]
) -> None:
    client, seams = http

    answer = await client.get("/workbench/search", params=params)

    assert answer.status_code == 422
    seams.searched.assert_not_awaited()


async def test_a_spent_window_asks_nothing_of_anyone(http: Any) -> None:
    client, seams = http
    seams.limiter.acquire.return_value = False

    answer = await client.get("/workbench/search", params={"q": "ana"})

    assert answer.status_code == 429
    seams.searched.assert_not_awaited()


async def test_the_section_switched_off_answers_nothing(http: Any) -> None:
    client, seams = http
    seams.enabled.return_value = False

    answer = await client.get("/workbench/search", params={"q": "ana"})

    assert answer.status_code == 403
    seams.searched.assert_not_awaited()
