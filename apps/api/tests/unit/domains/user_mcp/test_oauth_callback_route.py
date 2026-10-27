"""Unit tests for the OAuth callback route contract (user MCP servers).

The callback is a browser redirect target: whatever the authorization server
sends (denial, error, missing code, ``iss`` parameter), the user must land
back on the frontend with a meaningful marker — never on a bare 422.

Spec 2026-07-28 / RFC 9207: the ``iss`` parameter must reach the flow handler
so it can be validated against the recorded issuer.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.user_mcp import router as router_module
from src.domains.user_mcp.router import oauth_callback


@pytest.fixture
def forbid_handler(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Fail the test if the OAuth flow handler is even constructed."""

    class _Boom:
        _consume_state = AsyncMock(return_value=None)

        def __init__(self) -> None:
            raise AssertionError("MCPOAuthFlowHandler must not be constructed on this path")

    monkeypatch.setattr(router_module, "MCPOAuthFlowHandler", _Boom)
    return _Boom._consume_state


class TestCallbackErrorPaths:
    """Denial and error responses redirect to the frontend, never 422."""

    @pytest.mark.asyncio
    async def test_user_denial_redirects_with_denied_marker(self, forbid_handler):
        response = await oauth_callback(error="access_denied")

        assert response.status_code == 302
        location = response.headers["location"]
        assert location.startswith(settings.frontend_url)
        assert "mcp_oauth=denied" in location

    @pytest.mark.asyncio
    async def test_provider_error_redirects_with_generic_error(self, forbid_handler):
        """The provider-controlled error value is NEVER reflected in the
        redirect URL (it is free text from a third party)."""
        response = await oauth_callback(error="our_internal_db_said_no<script>")

        assert response.status_code == 302
        location = response.headers["location"]
        assert "mcp_oauth=error" in location
        assert "error=oauth_failed" in location
        assert "script" not in location

    @pytest.mark.asyncio
    async def test_missing_code_redirects_with_error(self, forbid_handler):
        response = await oauth_callback(state="some-state")

        forbid_handler.assert_awaited_once_with("some-state")
        assert response.status_code == 302
        assert "mcp_oauth=error" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_missing_state_redirects_with_error(self, forbid_handler):
        response = await oauth_callback(code="some-code")

        assert response.status_code == 302
        assert "mcp_oauth=error" in response.headers["location"]

    async def test_exchange_failure_never_logs_private_provider_text(self, monkeypatch):
        handler = AsyncMock()
        handler.__aenter__.return_value = handler
        handler.handle_callback.side_effect = RuntimeError("private-token")
        monkeypatch.setattr(router_module, "MCPOAuthFlowHandler", lambda: handler)
        log = MagicMock()
        monkeypatch.setattr(router_module, "logger", log)
        response = await oauth_callback(code="private-code", state="state", is_native=False)
        assert "oauth_failed" in response.headers["location"]
        assert "private-token" not in repr(log.error.call_args)
        assert log.error.call_args.kwargs["error_type"] == "RuntimeError"


class TestAuthorizeWiring:
    """``oauth_authorize`` must forward the stored issuer to the flow handler,
    otherwise the issuer-binding rule silently never triggers."""

    @pytest.mark.asyncio
    async def test_authorize_passes_stored_issuer(self, monkeypatch):
        from src.domains.user_mcp import authorization
        from src.domains.user_mcp.models import UserMCPAuthType
        from src.domains.user_mcp.router import oauth_authorize

        server = type(
            "Srv",
            (),
            {
                "id": uuid4(),
                "url": "https://mcp.example.com/mcp",
                "auth_type": UserMCPAuthType.OAUTH2.value,
                "oauth_metadata": {"requested_scopes": ""},
            },
        )()

        class _FakeService:
            def __init__(self, db: object) -> None:
                pass

            async def get_with_ownership_check(self, server_id, user_id):
                return server

            def get_decrypted_credentials(self, srv):
                return {
                    "client_id": "client-abc",
                    "client_secret": "sec",
                    "issuer": "https://auth-a.example.com",
                }

            async def cache_oauth_metadata(self, srv, metadata):
                return None

        initiate_flow_mock = AsyncMock(return_value=("https://auth/authorize?x=1", {"issuer": "i"}))

        class _FakeHandler:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc: object) -> None:
                return None

            initiate_flow = initiate_flow_mock

        monkeypatch.setattr(authorization, "UserMCPServerService", _FakeService)
        monkeypatch.setattr(authorization, "MCPOAuthFlowHandler", _FakeHandler)

        user = type("U", (), {"id": uuid4()})()
        await oauth_authorize(server_id=server.id, user=user, db=AsyncMock())

        assert initiate_flow_mock.call_args.kwargs["stored_issuer"] == "https://auth-a.example.com"


class TestCallbackNominalPath:
    """The ``iss`` parameter is forwarded to the flow handler (RFC 9207)."""

    @pytest.mark.asyncio
    async def test_iss_is_forwarded_to_handler(self, monkeypatch):
        server_id, user_id = uuid4(), uuid4()
        handle_callback_mock = AsyncMock(return_value=(server_id, user_id, "encrypted-creds"))

        class _FakeHandler:
            application_command_id = None

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc: object) -> None:
                return None

            handle_callback = handle_callback_mock

        monkeypatch.setattr(router_module, "MCPOAuthFlowHandler", _FakeHandler)
        update_creds = AsyncMock()
        monkeypatch.setattr(
            router_module.UserMCPServerService, "update_oauth_credentials", update_creds
        )

        response = await oauth_callback(
            code="auth-code", state="state-1", iss="https://auth.example.com"
        )

        assert response.status_code == 302
        assert "mcp_oauth=success" in response.headers["location"]
        assert handle_callback_mock.call_args.kwargs["iss"] == "https://auth.example.com"
        update_creds.assert_awaited_once_with(server_id, "encrypted-creds")
