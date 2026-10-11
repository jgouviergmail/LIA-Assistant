"""Private configuration responses never cache or disclose submitted values in errors."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request
from starlette.responses import Response

from src.core.exceptions import BaseAPIException
from src.domains.agents.application import command_router
from src.domains.agents.application.personal_mcp_configuration_schemas import (
    PersonalMCPConfigurationSubmit,
)


async def test_private_validation_failure_returns_only_public_error_code(monkeypatch):
    operation = AsyncMock(side_effect=ValueError("private-key"))
    monkeypatch.setattr(command_router, "serve_personal_mcp_configuration", operation)
    request = Request({"type": "http", "headers": []})
    response = Response()
    with pytest.raises(BaseAPIException) as failure:
        await command_router.configure_application_personal_mcp(
            uuid4(),
            request,
            response,
            PersonalMCPConfigurationSubmit(values={"api_key": "private-key"}),
            SimpleNamespace(id=uuid4()),
            AsyncMock(),
        )
    assert failure.value.status_code == 422
    assert failure.value.detail == {"error_code": "INVALID_INPUT"}
    assert failure.value.headers["Cache-Control"] == response.headers["Cache-Control"] == "no-store"
    assert "private-key" not in str(failure.value)


async def test_malformed_private_body_is_sanitized_before_route_entry(monkeypatch):
    application = FastAPI()
    application.include_router(command_router.router)
    application.dependency_overrides[command_router.get_current_active_session] = lambda: (
        SimpleNamespace(id=uuid4())
    )
    application.dependency_overrides[command_router.get_db] = lambda: AsyncMock()
    application.dependency_overrides[command_router.rate_limit_command_resume] = lambda: None
    operation = AsyncMock()
    monkeypatch.setattr(command_router, "serve_personal_mcp_configuration", operation)
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/application-commands/{uuid4()}/personal-mcp",
            json={"values": ["private-key", "https://example.org/private"]},
        )
    assert response.status_code == 422
    assert response.json() == {"detail": {"error_code": "INVALID_INPUT"}}
    assert response.headers["Cache-Control"] == "no-store"
    assert "private-key" not in response.text
    operation.assert_not_awaited()
