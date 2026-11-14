"""Updating a personal MCP server's authentication, read back from real PostgreSQL.

What the settings form and the assistant store when they switch a server to OAuth or move an
OAuth server (``credential_transition``): the row says ``auth_required``, keeps no secret of
the previous type and no token issued for another address, and the previous test verdict is
gone. The unit tests prove the decision on a mocked session; this proves the stored row.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.user_mcp.models import UserMCPAuthType, UserMCPServer, UserMCPServerStatus
from src.domains.user_mcp.schemas import UserMCPServerUpdate
from src.domains.user_mcp.service import UserMCPServerService
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


async def _server(
    db: AsyncSession,
    *,
    auth_type: UserMCPAuthType,
    credentials: dict[str, object],
    status: UserMCPServerStatus,
    oauth_metadata: dict[str, object] | None = None,
) -> UserMCPServer:
    user = UserFactory.create()
    db.add(user)
    await db.flush()
    server = UserMCPServer(
        user_id=user.id,
        name="Notes",
        url="https://notes.example.test/mcp",
        auth_type=auth_type.value,
        credentials_encrypted=encrypt_data(json.dumps(credentials)),
        status=status.value,
        last_error="Server returned an error response",
        oauth_metadata=oauth_metadata,
    )
    db.add(server)
    await db.flush()
    return server


async def _reload(db: AsyncSession, server: UserMCPServer) -> UserMCPServer:
    server_id = server.id  # read before the expiry: an expired attribute loads synchronously
    await db.flush()
    db.expire_all()
    stored = await db.get(UserMCPServer, server_id)
    assert stored is not None
    return stored


async def test_an_api_key_server_switched_to_oauth_awaits_authorization(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = await _server(
        async_session,
        auth_type=UserMCPAuthType.API_KEY,
        credentials={"header_name": "X-API-Key", "api_key": "sk-123"},
        status=UserMCPServerStatus.ERROR,
    )
    monkeypatch.setattr(UserMCPServerService, "_disconnect_from_pool", AsyncMock())

    await UserMCPServerService(async_session).update_server(
        server.id, server.user_id, UserMCPServerUpdate(auth_type=UserMCPAuthType.OAUTH2)
    )

    stored = await _reload(async_session, server)
    assert stored.auth_type == UserMCPAuthType.OAUTH2.value
    assert stored.status == UserMCPServerStatus.AUTH_REQUIRED.value
    assert stored.credentials_encrypted is None, "the API key never becomes OAuth credentials"
    assert stored.last_error is None


async def test_a_moved_oauth_server_keeps_its_client_and_loses_its_tokens(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = await _server(
        async_session,
        auth_type=UserMCPAuthType.OAUTH2,
        credentials={
            "client_id": "client-1",
            "client_secret": "secret-1",
            "access_token": "tok",
            "refresh_token": "ref",
        },
        status=UserMCPServerStatus.ACTIVE,
        oauth_metadata={
            "issuer": "https://auth.example.test",
            "authorization_endpoint": "https://auth.example.test/authorize",
            "token_endpoint": "https://auth.example.test/token",
            "requested_scopes": "read",
        },
    )
    monkeypatch.setattr(UserMCPServerService, "_disconnect_from_pool", AsyncMock())
    monkeypatch.setattr(
        "src.domains.user_mcp.service.validate_http_endpoint",
        AsyncMock(return_value=(True, None)),
    )

    await UserMCPServerService(async_session).update_server(
        server.id, server.user_id, UserMCPServerUpdate(url="https://other.example.test/mcp")
    )

    stored = await _reload(async_session, server)
    assert stored.url == "https://other.example.test/mcp"
    assert stored.status == UserMCPServerStatus.AUTH_REQUIRED.value
    assert stored.credentials_encrypted is not None
    assert json.loads(decrypt_data(stored.credentials_encrypted)) == {
        "client_id": "client-1",
        "client_secret": "secret-1",
    }
    # The endpoints belong to the old address: the next authorization rediscovers them.
    assert stored.oauth_metadata == {"requested_scopes": "read"}


async def test_an_oauth_server_moved_under_another_type_returns_without_the_old_discovery(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = await _server(
        async_session,
        auth_type=UserMCPAuthType.OAUTH2,
        credentials={"client_id": "client-1", "access_token": "tok"},
        status=UserMCPServerStatus.ACTIVE,
        oauth_metadata={
            "issuer": "https://auth.example.test",
            "authorization_endpoint": "https://auth.example.test/authorize",
            "token_endpoint": "https://auth.example.test/token",
            "requested_scopes": "read",
        },
    )
    monkeypatch.setattr(UserMCPServerService, "_disconnect_from_pool", AsyncMock())
    monkeypatch.setattr(
        "src.domains.user_mcp.service.validate_http_endpoint",
        AsyncMock(return_value=(True, None)),
    )
    service = UserMCPServerService(async_session)

    # Moved while it reads an API key, then brought back to OAuth: the cached endpoints
    # describe the old address, and the flow would reuse them as they stand.
    await service.update_server(
        server.id,
        server.user_id,
        UserMCPServerUpdate(
            auth_type=UserMCPAuthType.API_KEY,
            api_key="sk-1",
            url="https://other.example.test/mcp",
        ),
    )
    await service.update_server(
        server.id, server.user_id, UserMCPServerUpdate(auth_type=UserMCPAuthType.OAUTH2)
    )

    stored = await _reload(async_session, server)
    assert stored.url == "https://other.example.test/mcp"
    assert stored.status == UserMCPServerStatus.AUTH_REQUIRED.value
    assert stored.credentials_encrypted is None, "the API key never becomes OAuth credentials"
    assert stored.oauth_metadata == {"requested_scopes": "read"}
