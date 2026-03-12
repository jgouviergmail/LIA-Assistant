"""
MCP OAuth 2.1 Flow Handler.

Implements the MCP authentication specification:
- RFC 9728: Protected Resource Metadata discovery
- RFC 8414: Authorization Server Metadata
- RFC 7636: PKCE (S256 code challenge)
- RFC 7591: Dynamic Client Registration (optional)
- RFC 8707: Resource Indicators

Flow:
1. discover_auth_server() — find auth server from MCP endpoint
2. initiate_flow() — build authorization URL with PKCE
3. handle_callback() — exchange code for tokens

Phase: evolution F2.1 — MCP Per-User
Created: 2026-02-28
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
from uuid import UUID

import httpx
import structlog

from src.core.config import settings
from src.core.constants import (
    MCP_OAUTH_CLIENT_NAME,
    MCP_OAUTH_HTTP_TIMEOUT_SECONDS,
    MCP_USER_OAUTH_CALLBACK_PATH,
    MCP_USER_OAUTH_STATE_REDIS_PREFIX,
    MCP_USER_OAUTH_STATE_TTL_SECONDS,
)
from src.core.security.utils import (
    encrypt_data,
    generate_code_challenge,
    generate_code_verifier,
    generate_state_token,
)

logger = structlog.get_logger(__name__)


class MCPAuthServerMetadata:
    """Parsed OAuth authorization server metadata."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.issuer = data.get("issuer", "")
        self.authorization_endpoint = data.get("authorization_endpoint", "")
        self.token_endpoint = data.get("token_endpoint", "")
        self.registration_endpoint = data.get("registration_endpoint")
        self.scopes_supported = data.get("scopes_supported", [])
        self.code_challenge_methods_supported = data.get("code_challenge_methods_supported", [])
        self.raw = data

    @property
    def supports_pkce_s256(self) -> bool:
        return "S256" in self.code_challenge_methods_supported


class MCPOAuthFlowHandler:
    """
    Handles the MCP OAuth 2.1 authentication flow.

    Manages discovery, authorization, and token exchange
    for per-user MCP server authentication.

    Must be used as an async context manager to ensure HTTP client cleanup::

        async with MCPOAuthFlowHandler() as handler:
            url, meta = await handler.initiate_flow(...)
    """

    def __init__(self) -> None:
        self._http_client = httpx.AsyncClient(timeout=MCP_OAUTH_HTTP_TIMEOUT_SECONDS)

    async def __aenter__(self) -> MCPOAuthFlowHandler:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._http_client.aclose()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http_client.aclose()

    async def discover_auth_server(self, mcp_url: str) -> MCPAuthServerMetadata:
        """
        Discover the OAuth authorization server for an MCP endpoint.

        Follows the MCP auth spec:
        1. Try RFC 9728 Protected Resource Metadata (.well-known/oauth-protected-resource)
        2. Try sending unauthenticated request → parse WWW-Authenticate header
        3. Fetch authorization server metadata (RFC 8414)
        4. Fallback: .well-known/openid-configuration

        Raises:
            ValueError: If no authorization server can be discovered.
        """
        parsed = urlparse(mcp_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # Strategy 1: .well-known/oauth-protected-resource
        resource_metadata = await self._try_fetch_json(
            f"{base_url}/.well-known/oauth-protected-resource"
        )
        if resource_metadata and "authorization_servers" in resource_metadata:
            auth_server_url = resource_metadata["authorization_servers"][0]
            return await self._fetch_auth_server_metadata(auth_server_url)

        # Strategy 2: Unauthenticated request → WWW-Authenticate header
        try:
            resp = await self._http_client.get(mcp_url)
            if resp.status_code == 401:
                www_auth = resp.headers.get("www-authenticate", "")
                if "resource_metadata" in www_auth:
                    # Parse resource_metadata URL from header
                    rm_url = self._parse_www_authenticate_resource_metadata(www_auth)
                    if rm_url:
                        rm_data = await self._try_fetch_json(rm_url)
                        if rm_data and "authorization_servers" in rm_data:
                            auth_server_url = rm_data["authorization_servers"][0]
                            return await self._fetch_auth_server_metadata(auth_server_url)
        except httpx.HTTPError:
            pass

        # Strategy 3: .well-known/oauth-authorization-server (RFC 8414)
        metadata = await self._try_fetch_json(f"{base_url}/.well-known/oauth-authorization-server")
        if metadata and "authorization_endpoint" in metadata:
            return MCPAuthServerMetadata(metadata)

        # Strategy 4: .well-known/openid-configuration fallback
        metadata = await self._try_fetch_json(f"{base_url}/.well-known/openid-configuration")
        if metadata and "authorization_endpoint" in metadata:
            return MCPAuthServerMetadata(metadata)

        raise ValueError(
            f"Could not discover OAuth authorization server for {mcp_url}. "
            "The server may not support OAuth 2.1 authentication."
        )

    async def initiate_flow(
        self,
        server_id: UUID,
        user_id: UUID,
        mcp_url: str,
        cached_metadata: dict | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        requested_scopes: str | None = None,
    ) -> tuple[str, dict]:
        """
        Build the OAuth authorization URL with PKCE.

        Returns:
            Tuple of (authorization_url, metadata_to_cache).

        Raises:
            ValueError: If PKCE S256 is not supported or discovery fails.
        """
        # Discover or use cached auth server metadata
        if cached_metadata and "authorization_endpoint" in cached_metadata:
            metadata = MCPAuthServerMetadata(cached_metadata)
        else:
            metadata = await self.discover_auth_server(mcp_url)

        if not metadata.supports_pkce_s256:
            raise ValueError(
                "MCP OAuth server does not support PKCE S256 "
                "(required by MCP auth specification)"
            )

        # Resolve client_id via 3 strategies (per MCP spec priority)
        resolved_client_id = client_id
        resolved_client_secret = client_secret

        if not resolved_client_id:
            # Strategy 1: Dynamic Client Registration (RFC 7591)
            if metadata.registration_endpoint:
                reg_result = await self._try_dynamic_registration(
                    metadata.registration_endpoint, mcp_url
                )
                if reg_result:
                    resolved_client_id = reg_result.get("client_id")
                    resolved_client_secret = reg_result.get("client_secret")

        if not resolved_client_id:
            raise ValueError(
                "No client_id available for OAuth flow. "
                "Provide oauth_client_id in server configuration, "
                "or the auth server must support Dynamic Client Registration (RFC 7591)."
            )

        # Generate PKCE
        code_verifier = generate_code_verifier()
        code_challenge = generate_code_challenge(code_verifier)

        # Generate state token (CSRF)
        state = generate_state_token()

        # Store state in Redis (single-use, TTL 5min)
        # Sensitive fields (code_verifier, client_secret) are encrypted at rest
        state_data = {
            "server_id": str(server_id),
            "user_id": str(user_id),
            "code_verifier": encrypt_data(code_verifier),
            "mcp_url": mcp_url,
            "client_id": resolved_client_id,
            "client_secret": (
                encrypt_data(resolved_client_secret) if resolved_client_secret else None
            ),
            "token_endpoint": metadata.token_endpoint,
        }
        await self._store_state(state, state_data)

        # Build redirect URI
        callback_base = getattr(settings, "mcp_user_oauth_callback_base_url", None)
        if not callback_base:
            raise ValueError("MCP_USER_OAUTH_CALLBACK_BASE_URL must be configured for OAuth flows")
        redirect_uri = f"{callback_base}{MCP_USER_OAUTH_CALLBACK_PATH}"

        # Build authorization URL
        # Use user-specified scopes if provided, otherwise fall back to auto-discovered
        scope = requested_scopes or (
            " ".join(metadata.scopes_supported) if metadata.scopes_supported else ""
        )
        params = {
            "response_type": "code",
            "client_id": resolved_client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
            "scope": scope,
        }
        # RFC 8707: Resource Indicators
        params["resource"] = mcp_url

        # Remove empty params
        params = {k: v for k, v in params.items() if v}

        auth_url = f"{metadata.authorization_endpoint}?{urlencode(params)}"

        # Metadata to cache on the server record
        metadata_cache = {
            "authorization_endpoint": metadata.authorization_endpoint,
            "token_endpoint": metadata.token_endpoint,
            "registration_endpoint": metadata.registration_endpoint,
            "scopes_supported": metadata.scopes_supported,
            "code_challenge_methods_supported": metadata.code_challenge_methods_supported,
        }
        # Preserve user-specified scopes in cached metadata
        if requested_scopes:
            metadata_cache["requested_scopes"] = requested_scopes

        logger.info(
            "mcp_oauth_flow_initiated",
            server_id=str(server_id),
            user_id=str(user_id),
            auth_server=metadata.issuer,
        )

        return auth_url, metadata_cache

    async def handle_callback(
        self,
        code: str,
        state: str,
    ) -> tuple[UUID, UUID, str]:
        """
        Exchange authorization code for tokens.

        Returns:
            Tuple of (server_id, user_id, encrypted_credentials).

        Raises:
            ValueError: If state is invalid/expired or token exchange fails.
        """
        # Validate and consume state (single-use)
        state_data = await self._consume_state(state)
        if not state_data:
            raise ValueError("Invalid or expired OAuth state token")

        from src.core.security.utils import decrypt_data

        server_id = UUID(state_data["server_id"])
        user_id = UUID(state_data["user_id"])
        code_verifier = decrypt_data(state_data["code_verifier"])
        token_endpoint = state_data["token_endpoint"]
        client_id = state_data["client_id"]
        client_secret = (
            decrypt_data(state_data["client_secret"]) if state_data.get("client_secret") else None
        )
        mcp_url = state_data["mcp_url"]

        # Build redirect URI (must match initiate_flow)
        callback_base = getattr(settings, "mcp_user_oauth_callback_base_url", None)
        if not callback_base:
            raise ValueError("MCP_USER_OAUTH_CALLBACK_BASE_URL must be configured for OAuth flows")
        redirect_uri = f"{callback_base}{MCP_USER_OAUTH_CALLBACK_PATH}"

        # Exchange code for tokens
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
            "client_id": client_id,
            "resource": mcp_url,
        }
        if client_secret:
            token_data["client_secret"] = client_secret

        try:
            resp = await self._http_client.post(
                token_endpoint,
                data=token_data,
                headers={"Accept": "application/json"},
                timeout=MCP_OAUTH_HTTP_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as e:
            raise ValueError(f"Token exchange failed: {e}") from e

        if resp.status_code != 200:
            logger.error(
                "mcp_oauth_token_exchange_http_error",
                status_code=resp.status_code,
                response_body=resp.text[:200],
            )
            raise ValueError(
                f"Token exchange returned HTTP {resp.status_code}. "
                "Check server logs for details."
            )

        tokens = self._parse_token_response(resp)

        if "access_token" not in tokens:
            logger.error(
                "mcp_oauth_token_response_missing_access_token",
                response_keys=list(tokens.keys()),
            )
            raise ValueError(
                "Token endpoint response missing 'access_token'. " "Check server logs for details."
            )

        # Build credentials to store (encrypted)
        expires_in = int(tokens.get("expires_in", 3600))
        creds = {
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
            "expires_at": int(time.time()) + expires_in,
            "token_type": tokens.get("token_type", "Bearer"),
            "scope": tokens.get("scope", ""),
            "client_id": client_id,
            "client_secret": client_secret,
        }
        encrypted_creds = encrypt_data(json.dumps(creds))

        logger.info(
            "mcp_oauth_tokens_exchanged",
            server_id=str(server_id),
            user_id=str(user_id),
            has_refresh_token=bool(tokens.get("refresh_token")),
        )

        return server_id, user_id, encrypted_creds

    # =========================================================================
    # Private helpers
    # =========================================================================

    @staticmethod
    def _parse_token_response(resp: httpx.Response) -> dict[str, Any]:
        """Parse token endpoint response (JSON or form-urlencoded).

        Some providers (e.g., GitHub) return ``application/x-www-form-urlencoded``
        instead of JSON despite the ``Accept: application/json`` header.  This
        method tries JSON first, then falls back to form-urlencoded parsing.
        """
        content_type = resp.headers.get("content-type", "")

        # Try JSON first (standard OAuth 2.0/2.1)
        if "json" in content_type:
            result: dict[str, Any] = resp.json()
            return result

        # Try JSON anyway (some servers don't set Content-Type correctly)
        try:
            result = resp.json()
            return result
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: application/x-www-form-urlencoded (GitHub convention)
        parsed = parse_qs(resp.text, keep_blank_values=True)
        if "access_token" in parsed:
            return {k: v[0] for k, v in parsed.items()}

        logger.error(
            "mcp_oauth_token_unparseable_response",
            content_type=content_type,
            response_body=resp.text[:200],
        )
        raise ValueError(
            f"Token endpoint returned unparseable response "
            f"(Content-Type: {content_type}). Check server logs for details."
        )

    async def _try_fetch_json(self, url: str) -> dict[str, Any] | None:
        """Fetch a URL and parse as JSON, returning None on failure."""
        try:
            resp = await self._http_client.get(url)
            if resp.status_code == 200:
                result: dict[str, Any] = resp.json()
                return result
        except (httpx.HTTPError, json.JSONDecodeError):
            pass
        return None

    async def _fetch_auth_server_metadata(self, auth_server_url: str) -> MCPAuthServerMetadata:
        """Fetch OAuth authorization server metadata (RFC 8414).

        Discovery strategies (in order):
        1. RFC 8414: .well-known/oauth-authorization-server
        2. OpenID Connect: .well-known/openid-configuration
        3. Convention-based heuristic: {auth_server_url}/authorize + /access_token
           (for providers like GitHub that don't implement RFC 8414)
        """
        parsed = urlparse(auth_server_url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        # Strategy 1: .well-known/oauth-authorization-server (RFC 8414)
        metadata = await self._try_fetch_json(f"{base}/.well-known/oauth-authorization-server")
        if metadata and "authorization_endpoint" in metadata:
            return MCPAuthServerMetadata(metadata)

        # Strategy 2: .well-known/openid-configuration (OpenID Connect)
        metadata = await self._try_fetch_json(f"{base}/.well-known/openid-configuration")
        if metadata and "authorization_endpoint" in metadata:
            return MCPAuthServerMetadata(metadata)

        # Strategy 3: Convention-based heuristic
        # Many OAuth providers (e.g., GitHub) don't implement RFC 8414 metadata
        # discovery but expose endpoints as sub-paths of the auth server URL:
        #   {auth_server_url}/authorize   → authorization endpoint
        #   {auth_server_url}/access_token → token endpoint
        if parsed.path and parsed.path != "/":
            heuristic = await self._try_heuristic_endpoints(auth_server_url)
            if heuristic:
                return heuristic

        raise ValueError(f"Could not fetch auth server metadata from {auth_server_url}")

    async def _try_heuristic_endpoints(self, auth_server_url: str) -> MCPAuthServerMetadata | None:
        """Try convention-based endpoint discovery for non-RFC 8414 providers.

        Probes ``{auth_server_url}/authorize`` with a lightweight GET to verify
        the endpoint exists (any status except 404/5xx = valid).  If found,
        constructs metadata with ``/access_token`` as token endpoint (GitHub
        convention) and assumes PKCE S256 support (required by MCP spec).
        """
        authorize_url = f"{auth_server_url}/authorize"

        try:
            resp = await self._http_client.get(
                authorize_url,
                follow_redirects=False,
                params={"response_type": "code", "client_id": "_probe"},
            )
            if resp.status_code == 404 or resp.status_code >= 500:
                return None
        except httpx.HTTPError:
            return None

        token_url = f"{auth_server_url}/access_token"
        parsed = urlparse(auth_server_url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        logger.info(
            "mcp_oauth_heuristic_metadata_fallback",
            auth_server_url=auth_server_url,
            authorization_endpoint=authorize_url,
            token_endpoint=token_url,
        )

        return MCPAuthServerMetadata(
            {
                "issuer": base,
                "authorization_endpoint": authorize_url,
                "token_endpoint": token_url,
                "code_challenge_methods_supported": ["S256"],
            }
        )

    @staticmethod
    def _parse_www_authenticate_resource_metadata(header: str) -> str | None:
        """Extract resource_metadata URL from WWW-Authenticate header."""
        # Format: Bearer resource_metadata="https://..."
        for part in header.split(","):
            part = part.strip()
            if "resource_metadata=" in part:
                url = part.split("resource_metadata=", 1)[1].strip('" ')
                return url
        return None

    async def _try_dynamic_registration(
        self,
        registration_endpoint: str,
        mcp_url: str,
    ) -> dict[str, Any] | None:
        """Try Dynamic Client Registration (RFC 7591)."""
        callback_base = getattr(settings, "mcp_user_oauth_callback_base_url", None)
        if not callback_base:
            return None

        redirect_uri = f"{callback_base}{MCP_USER_OAUTH_CALLBACK_PATH}"

        try:
            resp = await self._http_client.post(
                registration_endpoint,
                json={
                    "client_name": MCP_OAUTH_CLIENT_NAME,
                    "redirect_uris": [redirect_uri],
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "none",
                    "scope": "",
                },
                timeout=MCP_OAUTH_HTTP_TIMEOUT_SECONDS,
            )
            if resp.status_code in (200, 201):
                data: dict[str, Any] = resp.json()
                logger.info(
                    "mcp_oauth_dynamic_registration_success",
                    registration_endpoint=registration_endpoint,
                    client_id=data.get("client_id"),
                )
                return data
        except httpx.HTTPError:
            pass

        return None

    @staticmethod
    async def _store_state(state: str, data: dict) -> None:
        """Store OAuth state in Redis (single-use, TTL 5min)."""
        from src.infrastructure.cache.redis import get_redis_session

        redis = await get_redis_session()
        key = f"{MCP_USER_OAUTH_STATE_REDIS_PREFIX}{state}"
        await redis.setex(key, MCP_USER_OAUTH_STATE_TTL_SECONDS, json.dumps(data))

    @staticmethod
    async def _consume_state(state: str) -> dict[str, Any] | None:
        """
        Consume OAuth state from Redis (atomic get-and-delete).

        Returns None if state is invalid or expired.
        """
        from src.infrastructure.cache.redis import get_redis_session

        redis = await get_redis_session()
        key = f"{MCP_USER_OAUTH_STATE_REDIS_PREFIX}{state}"

        # Atomic: get value and delete in pipeline
        pipe = redis.pipeline()
        pipe.get(key)
        pipe.delete(key)
        results = await pipe.execute()

        raw = results[0]
        if not raw:
            return None

        try:
            result: dict[str, Any] = json.loads(raw)
            return result
        except json.JSONDecodeError:
            return None
