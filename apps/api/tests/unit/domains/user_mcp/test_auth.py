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
