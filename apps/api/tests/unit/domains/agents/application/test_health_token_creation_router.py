"""The one-time secret endpoint binds the actual session and refuses supplied authority."""

from datetime import UTC, datetime
from importlib import import_module
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.application.command_service import CommandRejected
from src.domains.health_metrics.schemas import HealthMetricTokenCreateResponse
from src.domains.users.models import User

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("case", ["valid", "actor_body", "secret_body", "sql", "unknown"])
async def test_once_only_secret_http_route_is_private_and_session_bound(monkeypatch, case):
    module = import_module("src.domains.agents.application.command_router")
    monkeypatch.setattr(settings, "session_cookie_name", "test-session")
    actor, identity = User(id=uuid4(), is_active=True), uuid4()
    secret = HealthMetricTokenCreateResponse(
        id=identity,
        token="hm_private-browser",
        token_prefix="hm_public",
        label=None,
        created_at=datetime.now(UTC),
    )
    runner = AsyncMock(return_value=secret)
    if case == "sql":
        runner.side_effect = SQLAlchemyError("provider-private-secret")
    if case == "unknown":
        runner.side_effect = CommandRejected("COMPLETION_UNKNOWN")
    origin = object()
    binding = Mock(return_value=origin)
    monkeypatch.setattr(module, "serve_health_token_creation", runner)
    monkeypatch.setattr(module, "bind_browser_session", binding)
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_db] = lambda: "request-db"
    app.dependency_overrides[get_current_active_session] = lambda: actor
    app.dependency_overrides[module.rate_limit_command_resume] = lambda: None
    payload = (
        {"actor_id": str(uuid4())}
        if case == "actor_body"
        else {"token": "injected-secret"} if case == "secret_body" else {}
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={"test-session": "private-session"},
    ) as client:
        response = await client.post(f"/application-commands/{identity}/health-token", json=payload)
    if case in {"actor_body", "secret_body"}:
        assert response.status_code == 422
        runner.assert_not_awaited()
        return
    assert response.status_code == {"valid": 200, "sql": 503, "unknown": 409}[case]
    binding.assert_called_once_with(actor.id, "private-session")
    runner.assert_awaited_once_with("request-db", actor.id, identity, origin)
    assert response.headers["cache-control"] == "no-store"
    assert "private-session" not in response.text and "provider-private-secret" not in response.text
    if case == "valid":
        assert response.headers["pragma"] == "no-cache" and response.json()["token"] == secret.token
