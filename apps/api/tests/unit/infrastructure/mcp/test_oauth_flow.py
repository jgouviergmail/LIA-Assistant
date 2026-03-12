"""
Unit tests for MCPOAuthFlowHandler — metadata discovery strategies.

Tests the 3-strategy fallback in _fetch_auth_server_metadata():
1. RFC 8414 .well-known/oauth-authorization-server
2. OpenID Connect .well-known/openid-configuration
3. Convention-based heuristic ({auth_server_url}/authorize + /access_token)

Phase: evolution F2.1 — MCP Per-User
Created: 2026-03-02
"""

from unittest.mock import AsyncMock

import httpx
import pytest

from src.infrastructure.mcp.oauth_flow import MCPAuthServerMetadata, MCPOAuthFlowHandler


@pytest.fixture
def handler():
    """Create handler with mocked HTTP client."""
    h = MCPOAuthFlowHandler()
    h._http_client = AsyncMock(spec=httpx.AsyncClient)
    return h


class TestFetchAuthServerMetadata:
    """Test _fetch_auth_server_metadata() discovery strategies."""

    @pytest.mark.asyncio
    async def test_rfc8414_discovery(self, handler):
        """Strategy 1: RFC 8414 .well-known/oauth-authorization-server succeeds."""

        async def mock_get(url, **kwargs):
            resp = AsyncMock(spec=httpx.Response)
            if ".well-known/oauth-authorization-server" in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "issuer": "https://auth.example.com",
                    "authorization_endpoint": "https://auth.example.com/authorize",
                    "token_endpoint": "https://auth.example.com/token",
                    "code_challenge_methods_supported": ["S256"],
                }
            else:
                resp.status_code = 404
                resp.json.side_effect = ValueError("Not JSON")
            return resp

        handler._http_client.get = mock_get

        result = await handler._fetch_auth_server_metadata("https://auth.example.com")

        assert isinstance(result, MCPAuthServerMetadata)
        assert result.authorization_endpoint == "https://auth.example.com/authorize"
        assert result.token_endpoint == "https://auth.example.com/token"
        assert result.supports_pkce_s256

    @pytest.mark.asyncio
    async def test_openid_discovery(self, handler):
        """Strategy 2: OpenID Connect .well-known/openid-configuration succeeds."""

        async def mock_get(url, **kwargs):
            resp = AsyncMock(spec=httpx.Response)
            if ".well-known/openid-configuration" in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "issuer": "https://auth.example.com",
                    "authorization_endpoint": "https://auth.example.com/oidc/authorize",
                    "token_endpoint": "https://auth.example.com/oidc/token",
                    "code_challenge_methods_supported": ["S256"],
                }
            else:
                resp.status_code = 404
                resp.json.side_effect = ValueError("Not JSON")
            return resp

        handler._http_client.get = mock_get

        result = await handler._fetch_auth_server_metadata("https://auth.example.com")

        assert isinstance(result, MCPAuthServerMetadata)
        assert result.authorization_endpoint == "https://auth.example.com/oidc/authorize"

    @pytest.mark.asyncio
    async def test_heuristic_github_pattern(self, handler):
        """Strategy 3: Convention-based heuristic for GitHub-like providers."""

        async def mock_get(url, **kwargs):
            resp = AsyncMock(spec=httpx.Response)
            if ".well-known/" in url:
                resp.status_code = 404
                resp.json.side_effect = ValueError("Not JSON")
            elif "/authorize" in url:
                # GitHub returns 200 with login form or 302 redirect
                resp.status_code = 200
            else:
                resp.status_code = 404
                resp.json.side_effect = ValueError("Not JSON")
            return resp

        handler._http_client.get = mock_get

        result = await handler._fetch_auth_server_metadata("https://github.com/login/oauth")

        assert isinstance(result, MCPAuthServerMetadata)
        assert result.authorization_endpoint == "https://github.com/login/oauth/authorize"
        assert result.token_endpoint == "https://github.com/login/oauth/access_token"
        assert result.supports_pkce_s256
        assert result.issuer == "https://github.com"

    @pytest.mark.asyncio
    async def test_heuristic_skipped_when_no_path(self, handler):
        """Heuristic is skipped when auth_server_url has no meaningful path."""

        async def mock_get(url, **kwargs):
            resp = AsyncMock(spec=httpx.Response)
            resp.status_code = 404
            resp.json.side_effect = ValueError("Not JSON")
            return resp

        handler._http_client.get = mock_get

        with pytest.raises(ValueError, match="Could not fetch auth server metadata"):
            await handler._fetch_auth_server_metadata("https://auth.example.com")

    @pytest.mark.asyncio
    async def test_heuristic_authorize_returns_404(self, handler):
        """Heuristic fails when /authorize endpoint returns 404."""

        async def mock_get(url, **kwargs):
            resp = AsyncMock(spec=httpx.Response)
            resp.status_code = 404
            resp.json.side_effect = ValueError("Not JSON")
            return resp

        handler._http_client.get = mock_get

        with pytest.raises(ValueError, match="Could not fetch auth server metadata"):
            await handler._fetch_auth_server_metadata("https://github.com/login/oauth")

    @pytest.mark.asyncio
    async def test_heuristic_authorize_returns_5xx(self, handler):
        """Heuristic fails when /authorize endpoint returns 5xx."""

        async def mock_get(url, **kwargs):
            resp = AsyncMock(spec=httpx.Response)
            if "/authorize" in url and ".well-known" not in url:
                resp.status_code = 502
            else:
                resp.status_code = 404
                resp.json.side_effect = ValueError("Not JSON")
            return resp

        handler._http_client.get = mock_get

        with pytest.raises(ValueError, match="Could not fetch auth server metadata"):
            await handler._fetch_auth_server_metadata("https://github.com/login/oauth")

    @pytest.mark.asyncio
    async def test_heuristic_authorize_network_error(self, handler):
        """Heuristic fails when /authorize endpoint times out."""

        async def mock_get(url, **kwargs):
            if "/authorize" in url and ".well-known" not in url:
                raise httpx.ConnectTimeout("Connection timed out")
            resp = AsyncMock(spec=httpx.Response)
            resp.status_code = 404
            resp.json.side_effect = ValueError("Not JSON")
            return resp

        handler._http_client.get = mock_get

        with pytest.raises(ValueError, match="Could not fetch auth server metadata"):
            await handler._fetch_auth_server_metadata("https://github.com/login/oauth")

    @pytest.mark.asyncio
    async def test_heuristic_authorize_302_redirect(self, handler):
        """Heuristic succeeds when /authorize returns 302 (redirect to login)."""

        async def mock_get(url, **kwargs):
            resp = AsyncMock(spec=httpx.Response)
            if ".well-known/" in url:
                resp.status_code = 404
                resp.json.side_effect = ValueError("Not JSON")
            elif "/authorize" in url:
                resp.status_code = 302
            else:
                resp.status_code = 404
            return resp

        handler._http_client.get = mock_get

        result = await handler._fetch_auth_server_metadata("https://gitlab.com/oauth")

        assert result.authorization_endpoint == "https://gitlab.com/oauth/authorize"
        assert result.token_endpoint == "https://gitlab.com/oauth/access_token"

    @pytest.mark.asyncio
    async def test_heuristic_authorize_400_bad_request(self, handler):
        """Heuristic succeeds when /authorize returns 400 (missing params = endpoint exists)."""

        async def mock_get(url, **kwargs):
            resp = AsyncMock(spec=httpx.Response)
            if ".well-known/" in url:
                resp.status_code = 404
                resp.json.side_effect = ValueError("Not JSON")
            elif "/authorize" in url:
                resp.status_code = 400  # Missing required params
            else:
                resp.status_code = 404
            return resp

        handler._http_client.get = mock_get

        result = await handler._fetch_auth_server_metadata("https://example.com/oauth2")

        assert result.authorization_endpoint == "https://example.com/oauth2/authorize"

    @pytest.mark.asyncio
    async def test_rfc8414_takes_priority_over_heuristic(self, handler):
        """RFC 8414 discovery takes priority over heuristic (both would work)."""

        async def mock_get(url, **kwargs):
            resp = AsyncMock(spec=httpx.Response)
            if ".well-known/oauth-authorization-server" in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "issuer": "https://github.com",
                    "authorization_endpoint": "https://github.com/login/oauth/authorize",
                    "token_endpoint": "https://github.com/login/oauth/access_token",
                    "code_challenge_methods_supported": ["S256"],
                }
            elif "/authorize" in url:
                resp.status_code = 200
            else:
                resp.status_code = 404
                resp.json.side_effect = ValueError("Not JSON")
            return resp

        handler._http_client.get = mock_get

        result = await handler._fetch_auth_server_metadata("https://github.com/login/oauth")

        # Should come from RFC 8414, not heuristic
        assert result.issuer == "https://github.com"
        assert result.authorization_endpoint == "https://github.com/login/oauth/authorize"


class TestDiscoverAuthServer:
    """Test the top-level discover_auth_server() flow."""

    @pytest.mark.asyncio
    async def test_strategy1_protected_resource_metadata(self, handler):
        """Protected resource metadata → fetch auth server metadata."""
        call_count = 0

        async def mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = AsyncMock(spec=httpx.Response)
            if ".well-known/oauth-protected-resource" in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "authorization_servers": ["https://github.com/login/oauth"],
                }
            elif ".well-known/oauth-authorization-server" in url:
                resp.status_code = 404
                resp.json.side_effect = ValueError("Not JSON")
            elif ".well-known/openid-configuration" in url:
                resp.status_code = 404
                resp.json.side_effect = ValueError("Not JSON")
            elif "/authorize" in url:
                resp.status_code = 200  # Heuristic probe succeeds
            else:
                resp.status_code = 404
                resp.json.side_effect = ValueError("Not JSON")
            return resp

        handler._http_client.get = mock_get

        result = await handler.discover_auth_server("https://api.githubcopilot.com/mcp/")

        assert result.authorization_endpoint == "https://github.com/login/oauth/authorize"
        assert result.token_endpoint == "https://github.com/login/oauth/access_token"

    @pytest.mark.asyncio
    async def test_all_strategies_fail(self, handler):
        """All discovery strategies fail → ValueError."""

        async def mock_get(url, **kwargs):
            resp = AsyncMock(spec=httpx.Response)
            resp.status_code = 404
            resp.json.side_effect = ValueError("Not JSON")
            return resp

        handler._http_client.get = mock_get

        with pytest.raises(ValueError, match="Could not discover OAuth"):
            await handler.discover_auth_server("https://no-oauth.example.com/mcp")


class TestParseTokenResponse:
    """Test _parse_token_response() JSON and form-urlencoded parsing."""

    def test_json_content_type(self):
        """Standard JSON response parses correctly."""
        resp = httpx.Response(
            200,
            json={"access_token": "gho_abc", "token_type": "bearer", "scope": "repo"},
            headers={"content-type": "application/json"},
        )
        tokens = MCPOAuthFlowHandler._parse_token_response(resp)
        assert tokens["access_token"] == "gho_abc"
        assert tokens["token_type"] == "bearer"

    def test_json_without_content_type(self):
        """JSON response without proper Content-Type still parses."""
        resp = httpx.Response(
            200,
            content=b'{"access_token": "tok_123", "token_type": "bearer"}',
            headers={"content-type": "text/plain"},
        )
        tokens = MCPOAuthFlowHandler._parse_token_response(resp)
        assert tokens["access_token"] == "tok_123"

    def test_form_urlencoded_github_style(self):
        """GitHub-style form-urlencoded response parses correctly."""
        resp = httpx.Response(
            200,
            content=b"access_token=gho_xyz&token_type=bearer&scope=repo%2Cuser",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        tokens = MCPOAuthFlowHandler._parse_token_response(resp)
        assert tokens["access_token"] == "gho_xyz"
        assert tokens["token_type"] == "bearer"
        assert tokens["scope"] == "repo,user"

    def test_form_urlencoded_with_empty_values(self):
        """Form-urlencoded with empty scope still parses."""
        resp = httpx.Response(
            200,
            content=b"access_token=abc&token_type=bearer&scope=",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        tokens = MCPOAuthFlowHandler._parse_token_response(resp)
        assert tokens["access_token"] == "abc"
        assert tokens["scope"] == ""

    def test_unparseable_response_raises(self):
        """Completely unparseable response raises ValueError."""
        resp = httpx.Response(
            200,
            content=b"<html>Error</html>",
            headers={"content-type": "text/html"},
        )
        with pytest.raises(ValueError, match="unparseable response"):
            MCPOAuthFlowHandler._parse_token_response(resp)
