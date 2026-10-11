"""Application OAuth state never bypasses fresh approval guards or sends a code after refusal."""

from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.core.security.utils import encrypt_data
from src.infrastructure.mcp.oauth_flow import MCPOAuthFlowHandler


def stored(command):
    return {
        "server_id": str(uuid4()),
        "user_id": str(uuid4()),
        "code_verifier": encrypt_data("private-verifier"),
        "mcp_url": "https://example.org/mcp",
        "client_id": "client",
        "client_secret": None,
        "token_endpoint": "https://example.org/token",
        "issuer": None,
        "application_command_id": str(command),
    }


@pytest.mark.parametrize("command", [uuid4(), None, "malformed-private-context"])
async def test_application_state_without_guard_fails_closed_before_token_exchange(
    monkeypatch, command
):
    monkeypatch.setattr(settings, "mcp_user_oauth_callback_base_url", "https://lia.example.org")
    handler = MCPOAuthFlowHandler()
    await handler._http_client.aclose()
    handler._http_client = AsyncMock(spec=httpx.AsyncClient)
    monkeypatch.setattr(handler, "_consume_state", AsyncMock(return_value=stored(command)))
    monkeypatch.setattr(handler, "_is_safe_endpoint", AsyncMock(return_value=True))
    with pytest.raises(ValueError):
        await handler.handle_callback("private-code", "state")
    handler._http_client.post.assert_not_awaited()


async def test_fresh_refusal_after_dns_stops_token_exchange(monkeypatch):
    monkeypatch.setattr(settings, "mcp_user_oauth_callback_base_url", "https://lia.example.org")
    command = uuid4()
    handler = MCPOAuthFlowHandler()
    await handler._http_client.aclose()
    handler._http_client = AsyncMock(spec=httpx.AsyncClient)
    state = stored(command)
    monkeypatch.setattr(handler, "_consume_state", AsyncMock(return_value=state))
    monkeypatch.setattr(handler, "_is_safe_endpoint", AsyncMock(return_value=True))
    check = AsyncMock(side_effect=[None, AuthorizationError()])
    with pytest.raises(AuthorizationError):
        await handler.handle_callback("private-code", "state", application_check=check)
    assert check.await_count == 2
    handler._http_client.post.assert_not_awaited()


async def test_late_initiation_refusal_never_publishes_state_or_authorization_url(monkeypatch):
    monkeypatch.setattr(settings, "mcp_user_oauth_callback_base_url", "https://lia.example.org")
    handler = MCPOAuthFlowHandler()
    await handler._http_client.aclose()
    handler._http_client = AsyncMock(spec=httpx.AsyncClient)
    store = AsyncMock()
    monkeypatch.setattr(handler, "_store_state", store)
    check = AsyncMock(side_effect=[None, AuthorizationError()])
    with pytest.raises(AuthorizationError):
        await handler.initiate_flow(
            uuid4(),
            uuid4(),
            "https://example.org/mcp",
            client_id="client",
            cached_metadata={
                "authorization_endpoint": "https://example.org/authorize",
                "token_endpoint": "https://example.org/token",
                "code_challenge_methods_supported": ["S256"],
            },
            application_command_id=uuid4(),
            application_check=check,
        )
    store.assert_not_awaited()


@pytest.mark.parametrize("linked", [False, True])
async def test_success_preserves_legacy_path_and_requires_live_application_checks(
    monkeypatch, linked
):
    monkeypatch.setattr(settings, "mcp_user_oauth_callback_base_url", "https://lia.example.org")
    command = uuid4()
    state = stored(command)
    if not linked:
        state.pop("application_command_id")
    handler = MCPOAuthFlowHandler()
    await handler._http_client.aclose()
    handler._http_client = AsyncMock(spec=httpx.AsyncClient)
    handler._http_client.post.return_value = httpx.Response(
        200, json={"access_token": "private-token", "expires_in": 3600}
    )
    monkeypatch.setattr(handler, "_consume_state", AsyncMock(return_value=state))
    monkeypatch.setattr(handler, "_is_safe_endpoint", AsyncMock(return_value=True))
    check = AsyncMock()
    result = await handler.handle_callback("code", "state", application_check=check)
    assert check.await_count == (3 if linked else 0)
    assert handler.application_command_id == (command if linked else None)
    assert "private-token" not in result[2]
    handler._http_client.post.assert_awaited_once()


async def test_revocation_during_token_request_refuses_returning_credentials(monkeypatch):
    monkeypatch.setattr(settings, "mcp_user_oauth_callback_base_url", "https://lia.example.org")
    handler = MCPOAuthFlowHandler()
    await handler._http_client.aclose()
    handler._http_client = AsyncMock(spec=httpx.AsyncClient)
    handler._http_client.post.return_value = httpx.Response(
        200, json={"access_token": "private-token"}
    )
    monkeypatch.setattr(handler, "_consume_state", AsyncMock(return_value=stored(uuid4())))
    monkeypatch.setattr(handler, "_is_safe_endpoint", AsyncMock(return_value=True))
    check = AsyncMock(side_effect=[None, None, AuthorizationError()])
    with pytest.raises(AuthorizationError):
        await handler.handle_callback("code", "state", application_check=check)
    assert check.await_count == 3
    handler._http_client.post.assert_awaited_once()
