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
from contextlib import suppress
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
from uuid import UUID

import httpx
import structlog

from src.core.config import settings
from src.core.constants import (
    MCP_OAUTH_CLIENT_NAME,
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
from src.infrastructure.mcp.security import validate_http_endpoint

logger = structlog.get_logger(__name__)


# RFC 6749 §5.2 + RFC 8628 §3.5 error codes. An MCP authorization server is a
# third party: its response body is arbitrary text we do not control, so it must
# never reach the logs (SEC-030) — a provider can echo a code, a token, PII or a
# CRLF-injected line, and no generic PII filter can reliably sanitise opaque
# vendor text. Only a code matching this allowlist is logged; anything else
# (including `error_description`) is dropped.
_OAUTH_ERROR_CODES: frozenset[str] = frozenset(
    {
        "invalid_request",
        "invalid_client",
        "invalid_grant",
        "unauthorized_client",
        "unsupported_grant_type",
        "invalid_scope",
        "access_denied",
        "expired_token",
        "authorization_pending",
        "slow_down",
    }
)


# OIDC application_type derivation (spec 2026-07-28: clients MUST specify an
# appropriate application_type during Dynamic Client Registration). A callback
# served from a loopback host is a locally-hosted deployment → "native"; any
# public host → "web".
_NATIVE_CALLBACK_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})


def _derive_application_type(callback_base_url: str) -> str:
    """Derive the OIDC ``application_type`` from the OAuth callback base URL.

    Args:
        callback_base_url: Configured ``MCP_USER_OAUTH_CALLBACK_BASE_URL``.

    Returns:
        ``"native"`` for loopback-hosted callbacks, ``"web"`` otherwise.
    """
    host = urlparse(callback_base_url).hostname or ""
    return "native" if host in _NATIVE_CALLBACK_HOSTS else "web"


def safe_oauth_error_code_value(code: str | None) -> str | None:
    """Return ``code`` only when it is an RFC-defined OAuth error code.

    Shared allowlist gate (SEC-030): callback/redirect handlers must never
    log or reflect provider-controlled free text — only a known code survives.

    Args:
        code: Raw ``error`` value received from an authorization server.

    Returns:
        The code when allowlisted, ``None`` otherwise.
    """
    return code if isinstance(code, str) and code in _OAUTH_ERROR_CODES else None


def _safe_oauth_error_code(response: httpx.Response) -> str | None:
    """Extract the OAuth ``error`` code from a response, if it is a known one.

    Args:
        response: Token/authorization endpoint response.

    Returns:
        The RFC-defined error code when the body is JSON and carries one from
        :data:`_OAUTH_ERROR_CODES`; ``None`` otherwise. Never returns
        provider-controlled free text.
    """
    try:
        payload = response.json()
    except json.JSONDecodeError, ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    code = payload.get("error")
    return code if isinstance(code, str) and code in _OAUTH_ERROR_CODES else None


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
        self._http_client = httpx.AsyncClient(timeout=settings.mcp_oauth_http_timeout_seconds)

    async def __aenter__(self) -> MCPOAuthFlowHandler:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._http_client.aclose()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http_client.aclose()

    @staticmethod
    async def _is_safe_endpoint(url: str, *, phase: str) -> bool:
        """Whether a discovered OAuth endpoint may be contacted (SEC-008).

        The MCP server's own URL is validated when the server is created or
        updated (``user_mcp/service.py`` calls ``validate_http_endpoint``), but
        every endpoint reached *afterwards* comes out of a response body the
        server controls: ``authorization_servers[0]``, the ``resource_metadata``
        URL in a ``WWW-Authenticate`` header, ``authorization_endpoint``,
        ``token_endpoint``, ``registration_endpoint``. Without this check a
        user-registered MCP server could steer the backend at internal hosts, or
        receive an authorization code at an origin that was never approved.

        Reusing ``validate_http_endpoint`` keeps one single rule (HTTPS only,
        hostname blocklist, resolved IP not private/loopback/link-local/
        metadata/reserved) — the same one already enforced at registration, so a
        server that is legitimate today stays legitimate.

        Args:
            url: Endpoint URL to check.
            phase: Protocol phase, for the rejection log (no URL is logged).

        Returns:
            True when the endpoint is safe to contact.
        """
        is_valid, error = await validate_http_endpoint(url)
        if not is_valid:
            # The URL is attacker-influenced: log the host only, never the full
            # URL (it can carry query parameters).
            logger.warning(
                "mcp_oauth_endpoint_rejected",
                phase=phase,
                host=urlparse(url).hostname or "unparseable",
                reason=error,
            )
        return is_valid

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
        # SEC-008: `mcp_url` was validated when the server was registered, but
        # that was another point in time — DNS can have moved since (TOCTOU).
        # Revalidating immediately before the call costs one lookup and makes
        # the check hold at the moment it matters. A rejection only skips this
        # strategy; discovery continues with the well-known probes below, which
        # carry their own check.
        if await self._is_safe_endpoint(mcp_url, phase="www_authenticate_probe"):
            with suppress(httpx.HTTPError):
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
        stored_issuer: str | None = None,
    ) -> tuple[str, dict]:
        """
        Build the OAuth authorization URL with PKCE.

        Args:
            server_id: User MCP server identifier.
            user_id: Owner of the server.
            mcp_url: The MCP endpoint URL (RFC 8707 resource indicator).
            cached_metadata: Previously discovered auth server metadata.
            client_id: Stored or pre-registered OAuth client identifier.
            client_secret: Matching client secret, when one exists.
            requested_scopes: User-specified scopes overriding discovery.
            stored_issuer: Issuer the stored client credentials were obtained
                from. When the discovered issuer differs, the credentials are
                discarded and re-registration runs against the new server
                (spec 2026-07-28: credentials are bound to their issuer).

        Returns:
            Tuple of (authorization_url, metadata_to_cache).

        Raises:
            ValueError: If PKCE S256 is not supported, discovery fails, or the
                authorization server changed and no re-registration is possible.
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

        # Issuer binding (spec 2026-07-28): credentials from authorization
        # server A must never be sent to server B. Only a positively-detected
        # change triggers rebinding — a legacy record with no recorded issuer
        # (or metadata without one) stays untouched.
        issuer_changed = bool(
            stored_issuer and metadata.issuer and stored_issuer != metadata.issuer
        )
        if issuer_changed and resolved_client_id:
            logger.warning(
                "mcp_oauth_issuer_changed",
                server_id=str(server_id),
                previous_issuer_host=urlparse(stored_issuer or "").hostname or "unparseable",
                new_issuer_host=urlparse(metadata.issuer).hostname or "unparseable",
            )
            resolved_client_id = None
            resolved_client_secret = None

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
            if issuer_changed:
                raise ValueError(
                    "The authorization server for this MCP server has changed. "
                    "The stored OAuth client cannot be reused and re-registration "
                    "with the new server was not possible — update the server "
                    "configuration with credentials issued by the new "
                    "authorization server."
                )
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
            # RFC 9207: recorded issuer, validated against the callback `iss`
            "issuer": metadata.issuer or None,
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

        # SEC-002/SEC-008: `authorization_endpoint` comes from the server's own
        # metadata (or from its cached copy) and is handed to the browser, which
        # assigns it to `window.location`. An unvalidated value there is a
        # navigation primitive — `javascript:`/`data:` would execute in the LIA
        # origin, and a private host would turn the browser into an SSRF probe.
        # Validate before building the URL, and fail the flow rather than
        # returning something the frontend has to second-guess.
        if not await self._is_safe_endpoint(
            metadata.authorization_endpoint, phase="authorization_endpoint"
        ):
            raise ValueError(
                "The MCP server advertised an unusable authorization endpoint "
                "(it must be an HTTPS URL on a public host)."
            )

        auth_url = f"{metadata.authorization_endpoint}?{urlencode(params)}"

        # Metadata to cache on the server record
        metadata_cache = {
            "issuer": metadata.issuer,
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
        iss: str | None = None,
    ) -> tuple[UUID, UUID, str]:
        """
        Exchange authorization code for tokens.

        Args:
            code: Authorization code returned by the authorization server.
            state: CSRF state token (single-use, consumed from Redis).
            iss: Issuer identifier from the authorization response (RFC 9207).
                When present AND an issuer was recorded at initiation, the two
                MUST match or the code is never redeemed. Absent on either
                side, validation is skipped (many providers do not emit it).

        Returns:
            Tuple of (server_id, user_id, encrypted_credentials).

        Raises:
            ValueError: If state is invalid/expired, the ``iss`` parameter
                does not match the recorded issuer, or token exchange fails.
        """
        # Validate and consume state (single-use)
        state_data = await self._consume_state(state)
        if not state_data:
            raise ValueError("Invalid or expired OAuth state token")

        # RFC 9207 (spec 2026-07-28): validate a present `iss` against the
        # recorded issuer BEFORE the authorization code goes anywhere. Both
        # values are attacker-influenced URLs — log hosts only (SEC-030).
        recorded_issuer = state_data.get("issuer")
        if iss is not None and recorded_issuer and iss != recorded_issuer:
            logger.error(
                "mcp_oauth_iss_mismatch",
                expected_host=urlparse(recorded_issuer).hostname or "unparseable",
                received_host=urlparse(iss).hostname or "unparseable",
            )
            raise ValueError(
                "OAuth callback issuer mismatch: the authorization response "
                "did not come from the recorded authorization server. "
                "Refusing to redeem the authorization code."
            )

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

        # SEC-008: this POST carries the authorization code, the PKCE verifier
        # and possibly the client secret. `token_endpoint` was discovered from
        # the server's metadata and stored in Redis at initiation, so revalidate
        # it here — the destination must never be inferred from data we did not
        # re-check at the moment of use.
        if not await self._is_safe_endpoint(token_endpoint, phase="token_endpoint"):
            raise ValueError(
                "Refusing to send the authorization code to an unvalidated token endpoint."
            )

        try:
            resp = await self._http_client.post(
                token_endpoint,
                data=token_data,
                headers={"Accept": "application/json"},
                timeout=settings.mcp_oauth_http_timeout_seconds,
            )
        except httpx.HTTPError as e:
            raise ValueError(f"Token exchange failed: {e}") from e

        if resp.status_code != 200:
            logger.error(
                "mcp_oauth_token_exchange_http_error",
                status_code=resp.status_code,
                # SEC-030: never log the provider-controlled body.
                oauth_error=_safe_oauth_error_code(resp),
                content_type=resp.headers.get("content-type", "")[:64],
                body_bytes=len(resp.content),
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
            # Issuer binding: later flows compare this against the discovered
            # issuer and re-register when the authorization server changed.
            "issuer": recorded_issuer,
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
        with suppress(json.JSONDecodeError, ValueError):
            result = resp.json()
            return result

        # Fallback: application/x-www-form-urlencoded (GitHub convention)
        parsed = parse_qs(resp.text, keep_blank_values=True)
        if "access_token" in parsed:
            return {k: v[0] for k, v in parsed.items()}

        logger.error(
            "mcp_oauth_token_unparseable_response",
            content_type=content_type,
            # SEC-030: the body is unparseable *and* provider-controlled — the
            # worst case to echo. Size alone is enough to triage.
            body_bytes=len(resp.content),
        )
        raise ValueError(
            f"Token endpoint returned unparseable response "
            f"(Content-Type: {content_type}). Check server logs for details."
        )

    async def _try_fetch_json(self, url: str) -> dict[str, Any] | None:
        """Fetch a URL and parse as JSON, returning None on failure.

        SEC-008: this is the single funnel for every discovery GET, so the SSRF
        check lives here. A rejected endpoint returns ``None`` — the same shape
        as "not found" — which lets the caller fall through to the next
        discovery strategy instead of surfacing an SSRF probe as a hard error.
        """
        if not await self._is_safe_endpoint(url, phase="discovery"):
            return None
        with suppress(httpx.HTTPError, json.JSONDecodeError):
            resp = await self._http_client.get(url)
            if resp.status_code == 200:
                result: dict[str, Any] = resp.json()
                return result
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

        # SEC-008: this probe bypasses `_try_fetch_json`, so it needs its own
        # check. `auth_server_url` reaches here from `authorization_servers[0]`
        # — a value the MCP server controls — and the well-known probes above
        # returning nothing is exactly what routes a private address into this
        # fallback. Without this guard the heuristic path would still emit the
        # request the rest of the flow refuses to make.
        if not await self._is_safe_endpoint(authorize_url, phase="heuristic_probe"):
            return None

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

        # SEC-008: `registration_endpoint` is another server-supplied URL, and
        # this POST publishes our callback URI to it. Returning None keeps the
        # caller's existing "registration unavailable" path.
        if not await self._is_safe_endpoint(registration_endpoint, phase="registration_endpoint"):
            return None

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
                    # Spec 2026-07-28: MUST be specified; OIDC servers use it
                    # to validate redirect URIs, non-OIDC servers ignore it.
                    "application_type": _derive_application_type(callback_base),
                },
                timeout=settings.mcp_oauth_http_timeout_seconds,
            )
            if resp.status_code in (200, 201):
                data: dict[str, Any] = resp.json()
                logger.info(
                    "mcp_oauth_dynamic_registration_success",
                    registration_endpoint=registration_endpoint,
                    client_id=data.get("client_id"),
                )
                return data
        except httpx.HTTPError as e:
            logger.debug("dynamic_registration_failed", error=str(e))

        return None

    @staticmethod
    async def _store_state(state: str, data: dict) -> None:
        """Store OAuth state in Redis (single-use, TTL 5min)."""
        from src.infrastructure.cache.redis import get_redis_session

        redis = await get_redis_session()
        key = f"{MCP_USER_OAUTH_STATE_REDIS_PREFIX}{state}"
        await redis.set(key, json.dumps(data), ex=MCP_USER_OAUTH_STATE_TTL_SECONDS)

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
