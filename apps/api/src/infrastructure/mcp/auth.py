"""
MCP Authentication classes for per-user MCP servers.

Custom httpx2.Auth implementations for injecting authentication into the
MCP SDK v2 Streamable HTTP transport (the transport runs on httpx2; the
auth instances ride the httpx2.AsyncClient handed to it). The token-refresh
POST to the authorization server is an independent HTTP call and stays on
the httpx used by the rest of LIA.

Supports three strategies:
- MCPNoAuth: Pass-through (no auth header)
- MCPStaticTokenAuth: API Key or Bearer token (static header injection)
- MCPOAuth2Auth: OAuth 2.1 Bearer with auto-refresh on 401

Phase: evolution F2.1 — MCP Per-User
Created: 2026-02-28
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator, Callable, Coroutine, Generator
from contextlib import suppress
from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx
import httpx2
import structlog

from src.core.config import settings
from src.core.constants import (
    MCP_OAUTH_REFRESH_LOCK_TTL_SECONDS,
    MCP_USER_DEFAULT_API_KEY_HEADER,
)
from src.core.security.utils import decrypt_data, encrypt_data
from src.infrastructure.mcp.oauth_flow import safe_oauth_error_code
from src.infrastructure.mcp.utils import MCPAuthRequiredError

if TYPE_CHECKING:
    from src.domains.user_mcp.models import UserMCPServer

logger = structlog.get_logger(__name__)


class MCPNoAuth(httpx2.Auth):
    """Pass-through authentication (no headers added)."""

    def auth_flow(self, request: httpx2.Request) -> Generator[httpx2.Request, httpx2.Response]:
        yield request


class MCPStaticTokenAuth(httpx2.Auth):
    """
    Static token authentication for API Key or Bearer.

    Injects a fixed header (e.g., "Authorization: Bearer <token>"
    or "X-API-Key: <key>") into every request.
    """

    def __init__(self, header_name: str, header_value: str) -> None:
        self.header_name = header_name
        self.header_value = header_value

    def auth_flow(self, request: httpx2.Request) -> Generator[httpx2.Request, httpx2.Response]:
        request.headers[self.header_name] = self.header_value
        yield request


class MCPOAuth2Auth(httpx2.Auth):
    """
    OAuth 2.1 Bearer authentication with auto-refresh on 401.

    On first request, injects the stored access token.
    On 401 response, attempts to refresh using the refresh token.
    If refresh fails, marks the server as requiring re-authentication.

    Callbacks use their own DB sessions (not request-scoped) since
    token refresh can happen at any time during pool usage.
    """

    requires_response_body = False

    def __init__(
        self,
        server_id: UUID,
        get_creds_fn: Callable[[], Coroutine[Any, Any, dict | None]],
        update_creds_fn: Callable[[dict], Coroutine[Any, Any, None]],
        mark_auth_required_fn: Callable[[], Coroutine[Any, Any, None]],
        token_endpoint: str,
        client_id: str | None = None,
        client_secret: str | None = None,
        resource: str | None = None,
    ) -> None:
        self.server_id = server_id
        self._get_creds_fn = get_creds_fn
        self._update_creds_fn = update_creds_fn
        self._mark_auth_required_fn = mark_auth_required_fn
        self._token_endpoint = token_endpoint
        self._client_id = client_id
        self._client_secret = client_secret
        self._resource = resource

    async def async_auth_flow(
        self, request: httpx2.Request
    ) -> AsyncGenerator[httpx2.Request, httpx2.Response]:
        """Inject Bearer token, retry with refresh on 401."""
        creds = await self._get_creds_fn()
        if not creds or "access_token" not in creds:
            await self._mark_auth_required_fn()
            yield request
            return

        request.headers["Authorization"] = f"Bearer {creds['access_token']}"
        response = yield request

        if response.status_code == 401 and creds.get("refresh_token"):
            logger.info(
                "mcp_oauth_token_expired_refreshing",
                server_id=str(self.server_id),
            )
            new_creds = await self._refresh_tokens(creds)
            if new_creds:
                await self._update_creds_fn(new_creds)
                request.headers["Authorization"] = f"Bearer {new_creds['access_token']}"
                yield request
            else:
                await self._mark_auth_required_fn()
                logger.warning(
                    "mcp_oauth_refresh_failed",
                    server_id=str(self.server_id),
                )

    async def _refresh_tokens(self, creds: dict) -> dict | None:
        """Exchange refresh token for new access token.

        Uses a Redis distributed lock to prevent concurrent refreshes
        from invalidating tokens (same pattern as OAuthLock for Google).
        """
        lock_key = f"mcp_oauth_refresh_lock:{self.server_id}"
        lock_acquired = False
        # Redis unavailable — proceed without lock (best-effort)
        with suppress(Exception):
            from src.infrastructure.cache.redis import get_redis_session

            redis = await get_redis_session()
            lock_acquired = bool(
                await redis.set(lock_key, "1", ex=MCP_OAUTH_REFRESH_LOCK_TTL_SECONDS, nx=True)
            )
            if not lock_acquired:
                # Another request is already refreshing — re-read fresh creds
                logger.info(
                    "mcp_oauth_refresh_lock_contention",
                    server_id=str(self.server_id),
                )
                return await self._get_creds_fn()

        try:
            # Client identity: prefer the FRESH creds over the constructor
            # snapshot — a cached auth object must not replay a stale (or
            # missing) client_id after a re-registration updated the store.
            client_id = creds.get("client_id") or self._client_id
            client_secret = creds.get("client_secret") or self._client_secret

            data = {
                "grant_type": "refresh_token",
                "refresh_token": creds["refresh_token"],
            }
            if client_id:
                data["client_id"] = client_id
            if client_secret:
                data["client_secret"] = client_secret
            if self._resource:
                data["resource"] = self._resource

            async with httpx.AsyncClient(follow_redirects=False) as client:
                resp = await client.post(
                    self._token_endpoint,
                    data=data,
                    timeout=settings.mcp_oauth_http_timeout_seconds,
                )

            if resp.status_code != 200:
                logger.error(
                    "mcp_oauth_refresh_http_error",
                    server_id=str(self.server_id),
                    status=resp.status_code,
                    # SEC-030: allowlisted RFC code only, never the raw body.
                    # Its absence cost a full misdiagnosis on 2026-09-02 (a
                    # 400 caused by our own missing client_id was read as a
                    # server-side token expiry).
                    oauth_error=safe_oauth_error_code(resp),
                )
                return None

            token_data = resp.json()
            expires_in = int(token_data.get("expires_in", 3600))
            # Start from the STORED creds: the exchange only owns the token
            # fields. Rebuilding the dict from the response alone used to drop
            # client_id/client_secret/issuer, so every SECOND refresh posted
            # without client_id and died on 400 invalid_request (measured on
            # Era, 2026-09-02).
            return {
                **creds,
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token", creds["refresh_token"]),
                "expires_at": int(time.time()) + expires_in,
                "token_type": token_data.get("token_type", "Bearer"),
                "scope": token_data.get("scope", creds.get("scope", "")),
            }
        except Exception:
            logger.exception(
                "mcp_oauth_refresh_exception",
                server_id=str(self.server_id),
            )
            return None
        finally:
            if lock_acquired:
                # Lock will expire via TTL
                with suppress(Exception):
                    redis = await get_redis_session()
                    await redis.delete(lock_key)


async def load_user_mcp_creds(server_id: UUID, display_name: str) -> dict[str, Any] | None:
    """Fresh read of a user MCP server's stored OAuth credentials.

    Called on EVERY outgoing request by :class:`MCPOAuth2Auth`, so the status
    check below costs nothing extra — the row is already being read.

    Raises:
        MCPAuthRequiredError: When the stored status is ``auth_required``.
            Every call to that server is doomed until the user reconnects it;
            failing fast with the remedy replaces the 401 → refresh → 400
            dance this path used to replay on each call (six token-endpoint
            hits in one turn, measured 2026-09-02) and gives the model a
            message it can act on. A UI re-auth sets the status back to
            ``active``, which re-opens this path with no cache to invalidate.

    Args:
        server_id: The user MCP server row to read.
        display_name: Human-readable server name, used in the raised remedy.

    Returns:
        The decrypted credentials, or ``None`` when the server is gone or the
        stored blob is unreadable (the request then goes out unauthenticated,
        preserving the historical behaviour for servers with optional auth).
    """
    from src.domains.user_mcp.models import UserMCPServerStatus
    from src.domains.user_mcp.repository import UserMCPServerRepository
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        repo = UserMCPServerRepository(db)
        srv = await repo.get_by_id(server_id)
        if srv is None:
            return None
        if srv.status == UserMCPServerStatus.AUTH_REQUIRED.value:
            raise MCPAuthRequiredError(display_name)
        if srv.credentials_encrypted:
            try:
                result: dict[str, Any] = json.loads(decrypt_data(srv.credentials_encrypted))
                return result
            except ValueError, json.JSONDecodeError:
                return None
    return None


async def list_auth_required_server_names(user_id: UUID) -> list[str]:
    """Names of the user's enabled MCP servers awaiting re-authentication.

    The port through which agent context learns that a capability is one
    reconnection away rather than nonexistent: tool registration only loads
    ``active`` rows, so a disconnected server would otherwise vanish from the
    model's world (2026-09-02 incident — the model asserted "no access").
    Lives here, next to :func:`load_user_mcp_creds`, so the agents domain
    never imports the user_mcp domain directly (F009: no domain cycle).

    Args:
        user_id: The user whose servers to inspect.

    Returns:
        Sorted display names of enabled servers in ``auth_required`` status.
    """
    from src.domains.user_mcp.repository import UserMCPServerRepository
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        repo = UserMCPServerRepository(db)
        servers = await repo.get_auth_required_for_user(user_id)
        return [s.name for s in servers]


def build_auth_for_server(server: UserMCPServer) -> httpx2.Auth:
    """
    Factory: build the correct httpx2.Auth from a UserMCPServer's config.

    Decrypts stored credentials and instantiates the appropriate auth class.
    """
    from src.domains.user_mcp.models import UserMCPAuthType

    if server.auth_type == UserMCPAuthType.NONE.value:
        return MCPNoAuth()

    if not server.credentials_encrypted:
        logger.warning(
            "mcp_auth_missing_credentials",
            server_id=str(server.id),
            auth_type=server.auth_type,
        )
        return MCPNoAuth()

    try:
        creds = json.loads(decrypt_data(server.credentials_encrypted))
    except ValueError, json.JSONDecodeError:
        logger.error(
            "mcp_auth_decrypt_failed",
            server_id=str(server.id),
        )
        return MCPNoAuth()

    if server.auth_type == UserMCPAuthType.API_KEY.value:
        api_key = creds.get("api_key", "")
        if not api_key:
            logger.warning(
                "mcp_auth_empty_api_key",
                server_id=str(server.id),
            )
            return MCPNoAuth()
        return MCPStaticTokenAuth(
            header_name=creds.get("header_name", MCP_USER_DEFAULT_API_KEY_HEADER),
            header_value=api_key,
        )

    if server.auth_type == UserMCPAuthType.BEARER.value:
        token = creds.get("token", "")
        if not token:
            logger.warning(
                "mcp_auth_empty_bearer_token",
                server_id=str(server.id),
            )
            return MCPNoAuth()
        return MCPStaticTokenAuth(
            header_name="Authorization",
            header_value=f"Bearer {token}",
        )

    if server.auth_type == UserMCPAuthType.OAUTH2.value:
        # Build async callbacks for credential management
        server_id = server.id
        display_name = server.name

        async def get_creds() -> dict[str, Any] | None:
            return await load_user_mcp_creds(server_id, display_name)

        async def update_creds(new_creds: dict) -> None:
            from src.domains.user_mcp.service import UserMCPServerService

            encrypted = encrypt_data(json.dumps(new_creds))
            await UserMCPServerService.update_oauth_credentials(server_id, encrypted)

        async def mark_auth_required() -> None:
            from src.domains.user_mcp.service import UserMCPServerService

            await UserMCPServerService.mark_auth_required(server_id)

        # Extract OAuth metadata for token endpoint
        oauth_metadata = server.oauth_metadata or {}
        token_endpoint = oauth_metadata.get("token_endpoint", "")

        if not token_endpoint:
            logger.error(
                "mcp_oauth_missing_token_endpoint",
                server_id=str(server_id),
            )
            return MCPNoAuth()

        return MCPOAuth2Auth(
            server_id=server_id,
            get_creds_fn=get_creds,
            update_creds_fn=update_creds,
            mark_auth_required_fn=mark_auth_required,
            token_endpoint=token_endpoint,
            client_id=creds.get("client_id"),
            client_secret=creds.get("client_secret"),
            resource=server.url,
        )

    # Unknown auth type — pass through
    return MCPNoAuth()
