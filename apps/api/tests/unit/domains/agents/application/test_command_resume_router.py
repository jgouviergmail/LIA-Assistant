"""HTTP continuation accepts only an owned path id and actual cookie; proof stays on the server."""

from datetime import UTC, datetime, timedelta
from importlib import import_module
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.exceptions import AuthorizationError
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.application.command_status import ApplicationCommandStatus
from src.domains.agents.application.outcomes import ApplicationPhase
from src.domains.agents.application.secure_continuation import ContinuationCompletionUnknown
from src.domains.users.models import User

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "case", ["valid", "actor_body", "proof_body", "step_up", "sql", "redis", "unknown"]
)
async def test_resume_http_is_bound_typed_private_and_uses_the_existing_step_up_protocol(
    monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    module = import_module("src.domains.agents.application.command_router")
    monkeypatch.setattr(settings, "session_cookie_name", "custom-session")
    actor = User(id=uuid4(), is_active=True)
    command_id = uuid4()
    status = ApplicationCommandStatus(
        command_id=command_id,
        operation_id="device_sessions.revoke_others",
        phase=ApplicationPhase.RESUMING,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    runner = AsyncMock(return_value=status)
    failures = {
        "step_up": AuthorizationError(detail={"error_code": "STEP_UP_REQUIRED"}),
        "sql": SQLAlchemyError("private-cookie provider-secret"),
        "redis": RedisError("private-cookie provider-secret"),
        "unknown": ContinuationCompletionUnknown("private-cookie provider-secret"),
    }
    if case in failures:
        runner.side_effect = failures[case]
    origin = object()
    binding = Mock(return_value=origin)
    monkeypatch.setattr(module, "resume_secure_application_command", runner, raising=False)
    monkeypatch.setattr(module, "bind_browser_session", binding)
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_db] = lambda: "request-db"
    app.dependency_overrides[get_current_active_session] = lambda: actor
    limiter = getattr(module, "rate_limit_command_resume", None)
    if limiter is not None:
        app.dependency_overrides[limiter] = lambda: None
    payload = (
        {"actor_id": str(uuid4())}
        if case == "actor_body"
        else ({"step_up_at": datetime.now(UTC).isoformat()} if case == "proof_body" else {})
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={"custom-session": "private-cookie"},
    ) as client:
        response = await client.post(f"/application-commands/{command_id}/resume", json=payload)
    if case in {"actor_body", "proof_body"}:
        assert response.status_code == 422
        runner.assert_not_awaited()
        return
    expected_code = 403 if case == "step_up" else (503 if case in failures else 200)
    assert response.status_code == expected_code
    binding.assert_called_once_with(actor.id, "private-cookie")
    runner.assert_awaited_once_with("request-db", actor.id, command_id, origin)
    assert "private-cookie" not in response.text and "provider-secret" not in response.text
    assert response.headers["cache-control"] == "no-store"
    if case == "step_up":
        assert response.json()["detail"]["error"] == "step_up_required"
    elif case in failures:
        assert response.json()["detail"]["error_code"] == (
            "COMPLETION_UNKNOWN" if case == "unknown" else "DEPENDENCY_ERROR"
        )
