"""A finished OAuth consent stores its tokens only on the row it was asked for, on PostgreSQL.

The callback's write locks the row and compares its binding (oauth_binding): a server
switched to an API key, moved, or given another client while the person consented keeps
what it has, and the same row, discovery written meanwhile, takes the tokens.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.user_mcp import oauth_binding
from src.domains.user_mcp.models import UserMCPAuthType, UserMCPServer, UserMCPServerStatus
from src.domains.user_mcp.oauth_binding import (
    authorization_binding,
    persist_bound_oauth_credentials,
)
from src.domains.user_mcp.schemas import UserMCPServerUpdate
from src.domains.user_mcp.service import UserMCPServerService
from tests.helpers.committed_users import commit_owner

pytestmark = pytest.mark.integration

TOKENS = encrypt_data(json.dumps({"client_id": "client-1", "access_token": "fresh"}))


@pytest.fixture
def door_sessions(async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> AsyncEngine:
    """The callback's own sessions run on the test database."""

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    monkeypatch.setattr(oauth_binding, "get_db_context", session)
    return async_engine


async def _oauth_server(engine: AsyncEngine, identities: list[UUID]) -> UserMCPServer:
    owner = await commit_owner(engine, identities)
    async with AsyncSession(engine, expire_on_commit=False) as db:
        server = UserMCPServer(
            user_id=owner,
            name="Notes",
            url="https://notes.example.test/mcp",
            auth_type=UserMCPAuthType.OAUTH2.value,
            credentials_encrypted=encrypt_data(json.dumps({"client_id": "client-1"})),
            status=UserMCPServerStatus.AUTH_REQUIRED.value,
            oauth_metadata={"requested_scopes": "read"},
        )
        db.add(server)
        await db.commit()
        return server


async def _stored(engine: AsyncEngine, server: UserMCPServer) -> UserMCPServer:
    async with AsyncSession(engine, expire_on_commit=False) as db:
        row = await db.get(UserMCPServer, server.id)
        assert row is not None
        return row


async def test_the_row_the_consent_was_asked_for_takes_the_tokens(
    door_sessions: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    server = await _oauth_server(door_sessions, committed_user_ids)
    binding = authorization_binding(server, "client-1")
    # The flow caches the discovery while the person consents: not a change of the row.
    async with AsyncSession(door_sessions, expire_on_commit=False) as db:
        row = await db.get(UserMCPServer, server.id)
        assert row is not None
        row.oauth_metadata = {
            "requested_scopes": "read",
            "token_endpoint": "https://auth.example.test/token",
        }
        await db.commit()

    assert await persist_bound_oauth_credentials(server.id, server.user_id, binding, TOKENS)

    stored = await _stored(door_sessions, server)
    assert stored.status == UserMCPServerStatus.ACTIVE.value
    assert stored.credentials_encrypted == TOKENS


async def test_a_server_switched_to_an_api_key_during_the_consent_keeps_its_key(
    door_sessions: AsyncEngine, committed_user_ids: list[UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    server = await _oauth_server(door_sessions, committed_user_ids)
    binding = authorization_binding(server, "client-1")
    monkeypatch.setattr(UserMCPServerService, "_disconnect_from_pool", AsyncMock())
    async with AsyncSession(door_sessions, expire_on_commit=False) as db:
        await UserMCPServerService(db).update_server(
            server.id,
            server.user_id,
            UserMCPServerUpdate(auth_type=UserMCPAuthType.API_KEY, api_key="sk-new"),
        )
        await db.commit()

    assert not await persist_bound_oauth_credentials(server.id, server.user_id, binding, TOKENS)

    stored = await _stored(door_sessions, server)
    assert stored.auth_type == UserMCPAuthType.API_KEY.value
    assert stored.status == UserMCPServerStatus.ACTIVE.value
    assert stored.credentials_encrypted is not None
    assert json.loads(decrypt_data(stored.credentials_encrypted))["api_key"] == "sk-new"


async def test_a_server_moved_during_the_consent_is_not_given_the_old_grant(
    door_sessions: AsyncEngine, committed_user_ids: list[UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    server = await _oauth_server(door_sessions, committed_user_ids)
    binding = authorization_binding(server, "client-1")
    monkeypatch.setattr(UserMCPServerService, "_disconnect_from_pool", AsyncMock())
    monkeypatch.setattr(
        "src.domains.user_mcp.service.validate_http_endpoint",
        AsyncMock(return_value=(True, None)),
    )
    async with AsyncSession(door_sessions, expire_on_commit=False) as db:
        await UserMCPServerService(db).update_server(
            server.id, server.user_id, UserMCPServerUpdate(url="https://other.example.test/mcp")
        )
        await db.commit()

    assert not await persist_bound_oauth_credentials(server.id, server.user_id, binding, TOKENS)
    assert (await _stored(door_sessions, server)).status == UserMCPServerStatus.AUTH_REQUIRED.value


async def test_a_consent_started_before_bindings_is_held_to_the_type(
    door_sessions: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    server = await _oauth_server(door_sessions, committed_user_ids)
    assert await persist_bound_oauth_credentials(server.id, server.user_id, None, TOKENS)
    assert (await _stored(door_sessions, server)).credentials_encrypted == TOKENS
