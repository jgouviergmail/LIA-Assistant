"""
MCP Authentication classes for per-user MCP servers.

Custom httpx.Auth implementations for injecting authentication
into MCP SDK's streamablehttp_client(url, auth=auth) connections.

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
from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx
import structlog

from src.core.constants import (
    MCP_OAUTH_HTTP_TIMEOUT_SECONDS,
    MCP_OAUTH_REFRESH_LOCK_TTL_SECONDS,
    MCP_USER_DEFAULT_API_KEY_HEADER,
)
from src.core.security.utils import decrypt_data, encrypt_data

if TYPE_CHECKING:
    from src.domains.user_mcp.models import UserMCPServer

logger = structlog.get_logger(__name__)


class MCPNoAuth(httpx.Auth):
    """Pass-through authentication (no headers added)."""

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        yield request


class MCPStaticTokenAuth(httpx.Auth):
    """
    Static token authentication for API Key or Bearer.

    Injects a fixed header (e.g., "Authorization: Bearer <token>"
    or "X-API-Key: <key>") into every request.
    """

    def __init__(self, header_name: str, header_value: str) -> None:
        self.header_name = header_name
        self.header_value = header_value

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers[self.header_name] = self.header_value
        yield request


class MCPOAuth2Auth(httpx.Auth):
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
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
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
        try:
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
        except Exception:
            pass  # Redis unavailable — proceed without lock (best-effort)

        try:
            data = {
                "grant_type": "refresh_token",
                "refresh_token": creds["refresh_token"],
            }
            if self._client_id:
                data["client_id"] = self._client_id
            if self._client_secret:
                data["client_secret"] = self._client_secret
            if self._resource:
                data["resource"] = self._resource

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self._token_endpoint,
                    data=data,
                    timeout=MCP_OAUTH_HTTP_TIMEOUT_SECONDS,
                )

            if resp.status_code != 200:
                logger.error(
                    "mcp_oauth_refresh_http_error",
                    server_id=str(self.server_id),
                    status=resp.status_code,
                )
                return None

            token_data = resp.json()
            expires_in = int(token_data.get("expires_in", 3600))
            return {
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
                try:
                    redis = await get_redis_session()
                    await redis.delete(lock_key)
                except Exception:
                    pass  # Lock will expire via TTL


def build_auth_for_server(server: UserMCPServer) -> httpx.Auth:
    """
    Factory: build the correct httpx.Auth from a UserMCPServer's config.

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
    except (ValueError, json.JSONDecodeError):
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

        async def get_creds() -> dict[str, Any] | None:
            from src.infrastructure.database.session import get_db_context

            async with get_db_context() as db:
                from src.domains.user_mcp.repository import UserMCPServerRepository

                repo = UserMCPServerRepository(db)
                srv = await repo.get_by_id(server_id)
                if srv and srv.credentials_encrypted:
                    try:
                        result: dict[str, Any] = json.loads(decrypt_data(srv.credentials_encrypted))
                        return result
                    except (ValueError, json.JSONDecodeError):
                        return None
            return None

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
