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
from structlog.testing import capture_logs

from src.infrastructure.mcp.oauth_flow import (
    MCPAuthServerMetadata,
    MCPOAuthFlowHandler,
    _safe_oauth_error_code,
)
from tests.support.structlog_capture import fresh_module_logger


@pytest.fixture(autouse=True)
def _fresh_module_logger():
    """Keep `capture_logs` reliable under xdist — see `tests/support`."""
    from src.infrastructure.mcp import oauth_flow

    yield from fresh_module_logger(oauth_flow)


@pytest.fixture
def raw_handler():
    """Handler with a mocked HTTP client and the REAL SEC-008 SSRF guard.

    Used by the guard's own tests. They pass IP literals (127.0.0.1, 169.254…),
    which ``validate_http_endpoint`` classifies without any DNS lookup, so the
    tests stay hermetic.
    """
    h = MCPOAuthFlowHandler()
    h._http_client = AsyncMock(spec=httpx.AsyncClient)
    return h


@pytest.fixture
def handler(monkeypatch, raw_handler):
    """Handler with a mocked HTTP client and a permissive SSRF guard.

    The SEC-008 guard added to the discovery/token/registration paths calls
    ``validate_http_endpoint``, which resolves the hostname for real. These
    discovery tests use ``auth.example.com`` — a name that does not resolve — so
    leaving the guard active would make them depend on public DNS and assert the
    wrong thing (a rejected endpoint instead of a parsed metadata document).

    The guard is not left untested: ``TestSSRFGuardOnDiscoveredEndpoints`` below
    exercises it directly, and the underlying validator has its own suite in
    ``test_security.py``. Separating the two keeps each test on one
    responsibility.
    """
    monkeypatch.setattr(
        "src.infrastructure.mcp.oauth_flow.validate_http_endpoint",
        AsyncMock(return_value=(True, None)),
    )
    return raw_handler


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


class TestSSRFGuardOnDiscoveredEndpoints:
    """SEC-008: endpoints taken from a server's response must be revalidated.

    The MCP server's own URL is validated when the server is registered, but
    everything discovered afterwards — ``authorization_servers[0]``, the
    ``resource_metadata`` URL, ``authorization_endpoint``, ``token_endpoint``,
    ``registration_endpoint`` — comes out of a body that server controls.

    All targets below are IP literals, so no DNS lookup happens and the tests
    are hermetic.
    """

    @pytest.mark.asyncio
    async def test_discovery_skips_loopback_endpoint(self, raw_handler):
        """A loopback discovery URL is not fetched at all."""
        result = await raw_handler._try_fetch_json("http://127.0.0.1:8000/.well-known/x")

        assert result is None
        raw_handler._http_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_discovery_skips_cloud_metadata_endpoint(self, raw_handler):
        """The cloud metadata address is not fetched."""
        result = await raw_handler._try_fetch_json("http://169.254.169.254/latest/meta-data/")

        assert result is None
        raw_handler._http_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_discovery_skips_plain_http_endpoint(self, raw_handler):
        """HTTP (no TLS) is refused even on a public address."""
        result = await raw_handler._try_fetch_json("http://93.184.216.34/.well-known/x")

        assert result is None
        raw_handler._http_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_registration_is_skipped_for_private_endpoint(self, raw_handler):
        """Dynamic registration does not publish our callback to a private host."""
        result = await raw_handler._try_dynamic_registration(
            registration_endpoint="https://10.0.0.5/register",
            mcp_url="https://mcp.example.com/sse",
        )

        assert result is None
        raw_handler._http_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_guard_accepts_a_public_https_endpoint(self, raw_handler):
        """Control: a public HTTPS IP literal passes the guard.

        Without this, the tests above could pass for the wrong reason (a guard
        that rejects everything).
        """
        assert await raw_handler._is_safe_endpoint(
            "https://93.184.216.34/.well-known/x", phase="test"
        )

    @pytest.mark.asyncio
    async def test_heuristic_probe_skips_private_endpoint(self, raw_handler):
        """The convention-based fallback must not probe a private address.

        This path bypasses ``_try_fetch_json``, so it does NOT inherit the
        discovery guard — and it is precisely where a hostile server lands: the
        well-known probes return nothing (they are blocked or absent), which is
        exactly the condition that routes execution into the heuristic.
        """
        result = await raw_handler._try_heuristic_endpoints("https://10.0.0.5/oauth")

        assert result is None
        raw_handler._http_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_www_authenticate_probe_skips_private_endpoint(self, raw_handler):
        """A stored MCP URL is revalidated before the WWW-Authenticate probe.

        The URL was checked at registration; DNS may have moved since (TOCTOU).
        A rejection must skip only this strategy — discovery still tries the
        well-known probes, which is asserted by the absence of an exception.
        """
        with pytest.raises(ValueError, match="Could not discover"):
            await raw_handler.discover_auth_server("https://127.0.0.1:8000/sse")

        raw_handler._http_client.get.assert_not_called()


class TestEveryOutboundCallIsGuarded:
    """No outbound call in this module may skip the SEC-008 check.

    Enumerating the known call sites would only pin today's code: the failure
    mode is a NEW request added later without its guard. This walks the AST
    instead, so an unguarded call fails the test the moment it is written.
    """

    def test_no_unguarded_http_call_site(self):
        """Every ``self._http_client.get/post`` sits under a guard."""
        import ast
        import inspect as _inspect
        import textwrap

        from src.infrastructure.mcp import oauth_flow as module

        source = textwrap.dedent(_inspect.getsource(module))
        tree = ast.parse(source)

        # Functions whose body mentions the guard, by name.
        guarded_functions: set[str] = set()
        call_site_functions: list[tuple[str, int]] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            body_src = ast.dump(node)
            if "_is_safe_endpoint" in body_src:
                guarded_functions.add(node.name)
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                func = inner.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr in {"get", "post", "request"}
                    and isinstance(func.value, ast.Attribute)
                    and func.value.attr == "_http_client"
                ):
                    call_site_functions.append((node.name, inner.lineno))

        assert call_site_functions, "AST walk found no HTTP call sites — the probe is broken"

        unguarded = [
            f"{name}() at module line {lineno}"
            for name, lineno in call_site_functions
            if name not in guarded_functions
        ]
        assert not unguarded, (
            "these functions issue an outbound request without calling "
            f"_is_safe_endpoint: {unguarded}. Every URL reaching this module can "
            "come from an MCP server's response body (authorization_servers, "
            "resource_metadata, token/registration endpoints), so each call site "
            "must revalidate before connecting."
        )


class TestOAuthErrorCodeAllowlist:
    """SEC-030: only RFC-defined error codes may be extracted for logging."""

    def test_known_error_code_is_returned(self):
        """A code from RFC 6749 §5.2 is surfaced for diagnostics."""
        resp = httpx.Response(
            400,
            json={"error": "invalid_grant", "error_description": "code expired"},
        )
        assert _safe_oauth_error_code(resp) == "invalid_grant"

    def test_unknown_error_code_is_dropped(self):
        """A provider-invented code is NOT surfaced (it is free text)."""
        resp = httpx.Response(400, json={"error": "our_internal_db_said_no_42"})
        assert _safe_oauth_error_code(resp) is None

    def test_non_json_body_yields_no_code(self):
        """An HTML/opaque body yields no code rather than raising."""
        resp = httpx.Response(500, content=b"<html>boom</html>")
        assert _safe_oauth_error_code(resp) is None

    def test_json_array_body_yields_no_code(self):
        """A JSON body that is not an object is handled defensively."""
        resp = httpx.Response(400, json=["invalid_grant"])
        assert _safe_oauth_error_code(resp) is None


class TestNoProviderBodyReachesLogs:
    """SEC-030: an MCP authorization server's response body must never be logged.

    The body is third-party text: it can carry a code, a token, PII, or CRLF
    injection, and a generic PII filter cannot reliably sanitise opaque vendor
    content. These tests assert absence, which is the only assertion that
    actually protects the log stream.
    """

    _SENTINEL = "SENTINEL-c0de-and-t0ken-in-body"

    def test_unparseable_response_does_not_log_the_body(self):
        """The unparseable-response error logs size, never content."""
        resp = httpx.Response(
            200,
            content=f"<html>{self._SENTINEL}</html>".encode(),
            headers={"content-type": "text/html"},
        )

        with capture_logs() as logs:
            with pytest.raises(ValueError):
                MCPOAuthFlowHandler._parse_token_response(resp)

        assert logs, "the failure path must still emit a diagnostic event"
        serialized = repr(logs)
        assert self._SENTINEL not in serialized
        assert any(
            entry.get("body_bytes") for entry in logs
        ), "size must remain observable so an operator can still triage"
