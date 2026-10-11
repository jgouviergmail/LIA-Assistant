"""HTTP status forwards only the authenticated actor and transport-owned cookie."""

from datetime import UTC, datetime, timedelta
from importlib import import_module
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.application.command_status import ApplicationCommandStatus
from src.domains.agents.application.outcomes import ApplicationPhase
from src.domains.users.models import User

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("cookie_name", ["lia_session", "custom-session-name"])
@pytest.mark.parametrize("addressed", [False, True])
async def test_real_http_route_uses_session_principal_and_never_returns_cookie(
    monkeypatch: pytest.MonkeyPatch,
    cookie_name: str,
    addressed: bool,
) -> None:
    module = import_module("src.domains.agents.application.command_router")
    monkeypatch.setattr(settings, "session_cookie_name", cookie_name)
    actor, command_id = User(id=uuid4(), is_active=True), uuid4()
    reader = AsyncMock(
        return_value=ApplicationCommandStatus(
            command_id=command_id,
            operation_id="preferences.update",
            phase=ApplicationPhase.PENDING,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
    )
    origin = object()
    binding = Mock(return_value=origin)
    address = str(uuid4()) if addressed else None
    monkeypatch.setattr(module, "read_command_status", reader)
    monkeypatch.setattr(module, "bind_browser_session", binding)
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_db] = lambda: "request-db"
    app.dependency_overrides[get_current_active_session] = lambda: actor
    app.dependency_overrides[module.rate_limit_commands] = lambda: None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={cookie_name: "private-cookie"},
    ) as client:
        response = await client.get(
            f"/application-commands/{command_id}",
            params={"actor_id": str(uuid4())},
            headers={"X-Lia-Device-ID": address} if address is not None else {},
        )
    assert response.status_code == 200
    if address is None:
        binding.assert_called_once_with(actor.id, "private-cookie")
    else:
        binding.assert_called_once_with(actor.id, "private-cookie", device_id=address)
    reader.assert_awaited_once_with("request-db", actor.id, command_id, origin)
    assert "private-cookie" not in response.text and "binding" not in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("failure", ["sql", "redis"])
async def test_dependency_failures_are_finite_and_cannot_leak_private_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    from redis.exceptions import RedisError
    from sqlalchemy.exc import SQLAlchemyError

    module = import_module("src.domains.agents.application.command_router")
    exception = SQLAlchemyError if failure == "sql" else RedisError
    monkeypatch.setattr(
        module,
        "read_command_status",
        AsyncMock(side_effect=exception("private-cookie provider-key")),
    )
    monkeypatch.setattr(module, "bind_browser_session", Mock(return_value=None))
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_active_session] = lambda: User(id=uuid4(), is_active=True)
    app.dependency_overrides[module.rate_limit_commands] = lambda: None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/application-commands/{uuid4()}")
    assert response.status_code == 503
    assert response.json() == {"detail": {"error_code": "DEPENDENCY_ERROR"}}
    assert "private-cookie" not in response.text and "provider-key" not in response.text
    assert response.headers["cache-control"] == "no-store"
