"""Tests for MCP authentication classes (httpx.Auth custom implementations)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from src.infrastructure.mcp.auth import (
    MCPNoAuth,
    MCPOAuth2Auth,
    MCPStaticTokenAuth,
    build_auth_for_server,
)


class TestMCPNoAuth:
    """Tests for pass-through authentication."""

    def test_no_headers_added(self) -> None:
        """Should yield request without modifying headers."""
        auth = MCPNoAuth()
        request = httpx.Request("GET", "https://example.com")
        flow = auth.auth_flow(request)
        yielded_request = next(flow)
        assert yielded_request is request
        assert "Authorization" not in yielded_request.headers


class TestMCPStaticTokenAuth:
    """Tests for static token authentication (API Key / Bearer)."""

    def test_injects_custom_header(self) -> None:
        """Should inject the configured header name and value."""
        auth = MCPStaticTokenAuth("X-API-Key", "sk-test-123")
        request = httpx.Request("GET", "https://example.com")
        flow = auth.auth_flow(request)
        yielded_request = next(flow)
        assert yielded_request.headers["X-API-Key"] == "sk-test-123"

    def test_injects_authorization_header(self) -> None:
        """Should work with Authorization header for Bearer tokens."""
        auth = MCPStaticTokenAuth("Authorization", "Bearer eyJ-test")
        request = httpx.Request("GET", "https://example.com")
        flow = auth.auth_flow(request)
        yielded_request = next(flow)
        assert yielded_request.headers["Authorization"] == "Bearer eyJ-test"


class TestMCPOAuth2Auth:
    """Tests for OAuth 2.1 authentication with auto-refresh."""

    @pytest.fixture
    def oauth_auth(self):
        """Create MCPOAuth2Auth with mock callbacks."""
        return MCPOAuth2Auth(
            server_id=uuid4(),
            get_creds_fn=AsyncMock(
                return_value={"access_token": "valid_token", "refresh_token": "refresh_123"}
            ),
            update_creds_fn=AsyncMock(),
            mark_auth_required_fn=AsyncMock(),
            token_endpoint="https://auth.example.com/token",
            client_id="client-123",
        )

    @pytest.mark.asyncio
    async def test_injects_bearer_token(self, oauth_auth) -> None:
        """Should inject Bearer token on initial request."""
        request = httpx.Request("GET", "https://mcp.example.com/sse")
        flow = oauth_auth.async_auth_flow(request)

        yielded_request = await flow.__anext__()
        assert yielded_request.headers["Authorization"] == "Bearer valid_token"

    @pytest.mark.asyncio
    async def test_no_creds_marks_auth_required(self) -> None:
        """Should mark auth_required when no credentials available."""
        mark_fn = AsyncMock()
        auth = MCPOAuth2Auth(
            server_id=uuid4(),
            get_creds_fn=AsyncMock(return_value=None),
            update_creds_fn=AsyncMock(),
            mark_auth_required_fn=mark_fn,
            token_endpoint="https://auth.example.com/token",
        )
        request = httpx.Request("GET", "https://mcp.example.com/sse")
        flow = auth.async_auth_flow(request)
        await flow.__anext__()
        mark_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_access_token_marks_auth_required(self) -> None:
        """Should mark auth_required when access_token key is missing."""
        mark_fn = AsyncMock()
        auth = MCPOAuth2Auth(
            server_id=uuid4(),
            get_creds_fn=AsyncMock(return_value={"refresh_token": "rt"}),
            update_creds_fn=AsyncMock(),
            mark_auth_required_fn=mark_fn,
            token_endpoint="https://auth.example.com/token",
        )
        request = httpx.Request("GET", "https://mcp.example.com/sse")
        flow = auth.async_auth_flow(request)
        await flow.__anext__()
        mark_fn.assert_called_once()


class TestAuthRequiredShortCircuit:
    """A server marked ``auth_required`` fails fast with the remedy.

    Before this, every tool call on a dead server replayed the full
    401 → refresh → 400 dance (six token-endpoint hits in one turn, measured
    2026-09-02) and the model only ever saw "Server returned an error
    response" — so it told the user "I have no access" instead of "reconnect
    the server".
    """

    def _patch_db(self, server: object):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def fake_ctx():
            yield MagicMock()

        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=server)
        return (
            patch("src.infrastructure.database.session.get_db_context", fake_ctx),
            patch(
                "src.domains.user_mcp.repository.UserMCPServerRepository",
                return_value=repo,
            ),
        )

    async def test_auth_required_raises_with_remedy(self) -> None:
        """The error names the server and tells the model what to do."""
        from src.infrastructure.mcp.auth import load_user_mcp_creds
        from src.infrastructure.mcp.utils import MCPAuthRequiredError

        server = MagicMock()
        server.status = "auth_required"
        db_patch, repo_patch = self._patch_db(server)
        with db_patch, repo_patch, pytest.raises(MCPAuthRequiredError) as exc_info:
            await load_user_mcp_creds(uuid4(), "Era banque")

        message = str(exc_info.value)
        assert "Era banque" in message
        assert "re-authent" in message
        assert "reconnect" in message

    async def test_active_server_returns_decrypted_creds(self) -> None:
        """The nominal path is unchanged: fresh decrypted credentials."""
        from src.infrastructure.mcp.auth import load_user_mcp_creds

        server = MagicMock()
        server.status = "active"
        server.credentials_encrypted = "blob"
        db_patch, repo_patch = self._patch_db(server)
        with (
            db_patch,
            repo_patch,
            patch(
                "src.infrastructure.mcp.auth.decrypt_data",
                return_value=json.dumps({"access_token": "at"}),
            ),
        ):
            creds = await load_user_mcp_creds(uuid4(), "Era banque")

        assert creds == {"access_token": "at"}

    async def test_missing_server_returns_none(self) -> None:
        """A deleted server yields None (unauthenticated request), not a raise."""
        from src.infrastructure.mcp.auth import load_user_mcp_creds

        db_patch, repo_patch = self._patch_db(None)
        with db_patch, repo_patch:
            assert await load_user_mcp_creds(uuid4(), "gone") is None

    async def test_undecryptable_creds_return_none(self) -> None:
        """Corrupt credentials degrade to unauthenticated, as before."""
        from src.infrastructure.mcp.auth import load_user_mcp_creds

        server = MagicMock()
        server.status = "active"
        server.credentials_encrypted = "blob"
        db_patch, repo_patch = self._patch_db(server)
        with (
            db_patch,
            repo_patch,
            patch(
                "src.infrastructure.mcp.auth.decrypt_data",
                side_effect=ValueError("bad blob"),
            ),
        ):
            assert await load_user_mcp_creds(uuid4(), "Era banque") is None


class TestRefreshTokens:
    """Tests for the refresh-token exchange (the 2026-09-02 production defect).

    A successful refresh used to rebuild the stored credentials from the token
    response alone, silently dropping ``client_id`` / ``client_secret`` /
    ``issuer``. The NEXT refresh then posted without ``client_id`` and the
    authorization server answered 400 ``invalid_request`` forever (measured on
    Era: every first refresh succeeded, every second one failed).
    """

    def _auth(self, client_id: str | None = "client-123") -> MCPOAuth2Auth:
        return MCPOAuth2Auth(
            server_id=uuid4(),
            get_creds_fn=AsyncMock(),
            update_creds_fn=AsyncMock(),
            mark_auth_required_fn=AsyncMock(),
            token_endpoint="https://auth.example.com/token",
            client_id=client_id,
        )

    def _http_response(self, status_code: int, payload: dict) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = payload
        return resp

    def _patch_post(self, resp: MagicMock):
        """Patch httpx.AsyncClient used inside _refresh_tokens; capture POSTs."""
        client = AsyncMock()
        client.post.return_value = resp
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=client)
        cm.__aexit__ = AsyncMock(return_value=False)
        return patch("src.infrastructure.mcp.auth.httpx.AsyncClient", return_value=cm), client

    def _patch_no_redis(self):
        """Make the best-effort Redis lock deterministically unavailable."""
        return patch(
            "src.infrastructure.cache.redis.get_redis_session",
            side_effect=ConnectionError("no redis in unit tests"),
        )

    async def test_rotation_preserves_client_identity(self) -> None:
        """A refreshed credential set keeps every field the exchange does not own."""
        auth = self._auth()
        creds = {
            "access_token": "old_at",
            "refresh_token": "old_rt",
            "client_id": "client-123",
            "client_secret": "secret-xyz",
            "issuer": "https://auth.example.com",
            "scope": "read",
            "token_type": "Bearer",
        }
        resp = self._http_response(
            200, {"access_token": "new_at", "refresh_token": "new_rt", "expires_in": 60}
        )
        post_patch, _ = self._patch_post(resp)
        with post_patch, self._patch_no_redis():
            result = await auth._refresh_tokens(creds)

        assert result is not None
        assert result["access_token"] == "new_at"
        assert result["refresh_token"] == "new_rt"
        assert result["client_id"] == "client-123"
        assert result["client_secret"] == "secret-xyz"
        assert result["issuer"] == "https://auth.example.com"

    async def test_refresh_request_uses_freshest_client_identity(self) -> None:
        """The POST reads client identity from the FRESH creds, not only the
        constructor snapshot — an auth object built before a re-registration
        must not replay a stale (or missing) client_id."""
        auth = self._auth(client_id=None)
        creds = {
            "access_token": "old_at",
            "refresh_token": "old_rt",
            "client_id": "client-fresh",
        }
        resp = self._http_response(200, {"access_token": "new_at", "expires_in": 60})
        post_patch, client = self._patch_post(resp)
        with post_patch, self._patch_no_redis():
            await auth._refresh_tokens(creds)

        sent = client.post.call_args.kwargs["data"]
        assert sent["client_id"] == "client-fresh"

    async def test_second_refresh_still_sends_client_id(self) -> None:
        """The exact production signature: refresh once, feed the RESULT back
        as the stored creds, refresh again — the second POST must still carry
        client_id. Era timeline before the fix: 19:43 OK, 02:01 dead;
        05:52 re-auth, 08:55 OK, 09:58 dead."""
        auth = self._auth(client_id=None)
        creds = {
            "access_token": "at0",
            "refresh_token": "rt0",
            "client_id": "client-123",
            "client_secret": "secret-xyz",
        }
        resp = self._http_response(
            200, {"access_token": "at1", "refresh_token": "rt1", "expires_in": 60}
        )
        post_patch, client = self._patch_post(resp)
        with post_patch, self._patch_no_redis():
            rotated = await auth._refresh_tokens(creds)
            assert rotated is not None
            await auth._refresh_tokens(rotated)

        second_post = client.post.call_args_list[1].kwargs["data"]
        assert second_post["client_id"] == "client-123"
        assert second_post["client_secret"] == "secret-xyz"
        assert second_post["refresh_token"] == "rt1"

    async def test_refresh_keeps_previous_refresh_token_when_not_rotated(self) -> None:
        """A response without refresh_token keeps the stored one (no rotation)."""
        auth = self._auth()
        creds = {"access_token": "old_at", "refresh_token": "old_rt", "client_id": "c"}
        resp = self._http_response(200, {"access_token": "new_at", "expires_in": 60})
        post_patch, _ = self._patch_post(resp)
        with post_patch, self._patch_no_redis():
            result = await auth._refresh_tokens(creds)

        assert result is not None
        assert result["refresh_token"] == "old_rt"

    async def test_http_error_logs_oauth_error_code(self) -> None:
        """A refresh rejection logs the RFC error code — the datum whose absence
        cost a full misdiagnosis (Era's 400 read as a server-side expiry)."""
        auth = self._auth()
        creds = {"access_token": "a", "refresh_token": "r", "client_id": "c"}
        resp = self._http_response(
            400, {"error": "invalid_request", "error_description": "vendor text"}
        )
        post_patch, _ = self._patch_post(resp)
        with (
            post_patch,
            self._patch_no_redis(),
            patch("src.infrastructure.mcp.auth.logger") as mock_logger,
        ):
            result = await auth._refresh_tokens(creds)

        assert result is None
        assert mock_logger.error.call_args.kwargs["oauth_error"] == "invalid_request"

    async def test_http_error_unknown_code_is_not_logged(self) -> None:
        """Vendor free-text never reaches the logs — only allowlisted codes."""
        auth = self._auth()
        creds = {"access_token": "a", "refresh_token": "r", "client_id": "c"}
        resp = self._http_response(400, {"error": "weird_vendor_thing"})
        post_patch, _ = self._patch_post(resp)
        with (
            post_patch,
            self._patch_no_redis(),
            patch("src.infrastructure.mcp.auth.logger") as mock_logger,
        ):
            result = await auth._refresh_tokens(creds)

        assert result is None
        assert mock_logger.error.call_args.kwargs["oauth_error"] is None


class TestBuildAuthForServer:
    """Tests for the build_auth_for_server factory."""

    def _make_server(self, auth_type="none", credentials_encrypted=None, oauth_metadata=None):
        """Create a mock server object."""
        server = MagicMock()
        server.id = uuid4()
        server.auth_type = auth_type
        server.credentials_encrypted = credentials_encrypted
        server.url = "https://mcp.example.com/sse"
        server.oauth_metadata = oauth_metadata
        return server

    def test_none_auth_returns_no_auth(self) -> None:
        """Should return MCPNoAuth for 'none' auth type."""
        server = self._make_server(auth_type="none")
        auth = build_auth_for_server(server)
        assert isinstance(auth, MCPNoAuth)

    @patch("src.infrastructure.mcp.auth.decrypt_data")
    def test_api_key_returns_static_token(self, mock_decrypt) -> None:
        """Should return MCPStaticTokenAuth for API key."""
        mock_decrypt.return_value = json.dumps({"header_name": "X-API-Key", "api_key": "sk-123"})
        server = self._make_server(
            auth_type="api_key",
            credentials_encrypted="encrypted_data",
        )
        auth = build_auth_for_server(server)
        assert isinstance(auth, MCPStaticTokenAuth)
        assert auth.header_name == "X-API-Key"
        assert auth.header_value == "sk-123"

    @patch("src.infrastructure.mcp.auth.decrypt_data")
    def test_bearer_returns_static_token(self, mock_decrypt) -> None:
        """Should return MCPStaticTokenAuth with Authorization header for Bearer."""
        mock_decrypt.return_value = json.dumps({"token": "eyJ-test"})
        server = self._make_server(
            auth_type="bearer",
            credentials_encrypted="encrypted_data",
        )
        auth = build_auth_for_server(server)
        assert isinstance(auth, MCPStaticTokenAuth)
        assert auth.header_name == "Authorization"
        assert "Bearer eyJ-test" in auth.header_value

    @patch("src.infrastructure.mcp.auth.decrypt_data")
    def test_oauth2_returns_oauth_auth(self, mock_decrypt) -> None:
        """Should return MCPOAuth2Auth for OAuth2 auth type."""
        mock_decrypt.return_value = json.dumps({"access_token": "at", "refresh_token": "rt"})
        server = self._make_server(
            auth_type="oauth2",
            credentials_encrypted="encrypted_data",
            oauth_metadata={"token_endpoint": "https://auth.example.com/token"},
        )
        auth = build_auth_for_server(server)
        assert isinstance(auth, MCPOAuth2Auth)
        assert auth._token_endpoint == "https://auth.example.com/token"

    @patch("src.infrastructure.mcp.auth.decrypt_data")
    def test_oauth2_missing_token_endpoint_returns_no_auth(self, mock_decrypt) -> None:
        """Should return MCPNoAuth when OAuth2 token_endpoint is empty."""
        mock_decrypt.return_value = json.dumps({"access_token": "at", "refresh_token": "rt"})
        server = self._make_server(
            auth_type="oauth2",
            credentials_encrypted="encrypted_data",
            oauth_metadata={},  # No token_endpoint
        )
        auth = build_auth_for_server(server)
        assert isinstance(auth, MCPNoAuth)

    def test_missing_credentials_returns_no_auth(self) -> None:
        """Should return MCPNoAuth when credentials are missing."""
        server = self._make_server(auth_type="api_key", credentials_encrypted=None)
        auth = build_auth_for_server(server)
        assert isinstance(auth, MCPNoAuth)

    @patch("src.infrastructure.mcp.auth.decrypt_data", side_effect=ValueError("bad"))
    def test_decrypt_failure_returns_no_auth(self, mock_decrypt) -> None:
        """Should return MCPNoAuth when decryption fails."""
        server = self._make_server(
            auth_type="api_key",
            credentials_encrypted="bad_data",
        )
        auth = build_auth_for_server(server)
        assert isinstance(auth, MCPNoAuth)
