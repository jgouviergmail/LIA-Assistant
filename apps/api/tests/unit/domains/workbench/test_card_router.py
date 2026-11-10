"""The native-card admission is authenticated, capability-gated and bounded."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from src.core.content_source import content_source_binding
from src.core.exceptions import BaseAPIException
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.users.models import User
from src.domains.workbench import card_opening
from src.domains.workbench.card_targets import (
    CARD_TOKEN_MAX_CHARS,
    CardTargetKind,
    CardToolTarget,
    SignedCardTarget,
    sign_card_target,
)
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.router import router

pytestmark = pytest.mark.unit


@dataclass
class _Credentials:
    account_binding: str = "grant-a"


@dataclass
class _Provider:
    credentials: _Credentials


@dataclass
class _State:
    enabled: bool = True
    limited: bool = False
    opened: int = 0
    current_binding: str = "grant-a"


async def _handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, BaseAPIException)
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers
    )


@pytest.fixture
async def http(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[AsyncClient, _State, str]]:
    state = _State()
    user = User(id=uuid4())

    async def enabled(*args: object, **kwargs: object) -> bool:
        return state.enabled

    class Limiter:
        async def acquire(self, *args: object, **kwargs: object) -> bool:
            return not state.limited

    async def limiter() -> Limiter:
        return Limiter()

    @asynccontextmanager
    async def provider(
        tool: WorkbenchTool, user_id: UUID, *, fresh: bool = False
    ) -> AsyncIterator[ActiveClient]:
        assert user_id == user.id and tool == WorkbenchTool.FILES and fresh
        state.opened += 1
        yield ActiveClient(
            _Provider(_Credentials(state.current_binding)), ConnectorType.GOOGLE_DRIVE, None
        )

    monkeypatch.setattr("src.domains.feature_switches.guard.is_capability_enabled", enabled)
    monkeypatch.setattr("src.domains.auth.dependencies.get_rate_limiter", limiter)
    monkeypatch.setattr(card_opening, "open_tool_client", provider)
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(BaseAPIException, _handler)
    app.dependency_overrides[get_current_active_session_for_stream] = lambda: user
    envelope = SignedCardTarget(
        target=CardToolTarget(kind=CardTargetKind.FILE, item_id="actual-file"),
        provider=ConnectorType.GOOGLE_DRIVE,
        source_binding=content_source_binding(_Provider(_Credentials())),
    )
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        yield client, state, sign_card_target(envelope, user.id)


async def test_click_admits_same_source_and_refuses_a_later_account_switch(
    http: tuple[AsyncClient, _State, str],
) -> None:
    client, state, token = http
    response = await client.post("/workbench/card-target", json={"token": token})
    assert response.status_code == 200 and response.json()["target"]["item_id"] == "actual-file"
    state.current_binding = "another-account"
    response = await client.post("/workbench/card-target", json={"token": token})
    assert response.json() == {"available": False, "target": None, "reason": "source_changed"}
    assert state.opened == 2


@pytest.mark.parametrize("gate,status", [("capability", 403), ("rate", 429)])
async def test_off_or_rate_limited_never_opens_a_client(
    http: tuple[AsyncClient, _State, str], gate: str, status: int
) -> None:
    client, state, token = http
    state.enabled = gate != "capability"
    state.limited = gate == "rate"
    response = await client.post("/workbench/card-target", json={"token": token})
    assert response.status_code == status and state.opened == 0


async def test_browser_cannot_supply_its_own_target_or_unbounded_token(
    http: tuple[AsyncClient, _State, str],
) -> None:
    client, state, token = http
    for body in (
        {"token": token, "target": {"item_id": "guessed"}},
        {"token": "x" * (CARD_TOKEN_MAX_CHARS + 1)},
    ):
        response = await client.post("/workbench/card-target", json=body)
        assert response.status_code == 422
    assert state.opened == 0
