"""The production auth factory must use compare-and-write, including invalid grants."""

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.infrastructure.mcp.auth import build_auth_for_server


async def test_factory_binds_original_owner_url_and_guarded_persistence(monkeypatch):
    owner, server_id = uuid4(), uuid4()
    server = MagicMock(
        id=server_id,
        user_id=owner,
        name="target",
        auth_type="oauth2",
        credentials_encrypted="cipher",
        url="https://example.org/mcp",
        oauth_metadata={"token_endpoint": "https://example.org/token"},
    )
    monkeypatch.setattr(
        "src.infrastructure.mcp.auth.decrypt_data", lambda _: json.dumps({"access_token": "token"})
    )
    writer = AsyncMock(return_value=False)
    monkeypatch.setattr("src.domains.user_mcp.oauth_refresh.persist_matching_oauth_refresh", writer)
    auth = build_auth_for_server(server)
    server.url = "https://later.example/mcp"
    old, new = {"access_token": "token"}, {"access_token": "replacement"}
    assert not await auth._guarded_persistence(old, new)
    writer.assert_awaited_once_with(
        server_id, owner, "https://example.org/token", "https://example.org/mcp", old, new
    )
    await auth._mark_required(old)
    assert writer.call_args.args[-2:] == (old, None)


async def test_retired_client_never_receives_credentials_for_a_new_endpoint(monkeypatch):
    from contextlib import asynccontextmanager

    import pytest

    from src.infrastructure.mcp.auth import MCPAuthRequiredError, load_user_mcp_creds

    owner, server_id = uuid4(), uuid4()
    row = MagicMock(
        id=server_id,
        user_id=owner,
        auth_type="oauth2",
        status="active",
        url="https://new.example/mcp",
        oauth_metadata={"token_endpoint": "https://new.example/token"},
        credentials_encrypted="new-private-credentials",
    )
    repository = MagicMock()
    repository.get_by_id = AsyncMock(return_value=row)

    @asynccontextmanager
    async def database():
        yield AsyncMock()

    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    monkeypatch.setattr(
        "src.domains.user_mcp.repository.UserMCPServerRepository", lambda _: repository
    )
    decrypt = MagicMock()
    monkeypatch.setattr("src.infrastructure.mcp.auth.decrypt_data", decrypt)
    with pytest.raises(MCPAuthRequiredError):
        await load_user_mcp_creds(
            server_id,
            "target",
            expected_binding=(owner, "https://old.example/mcp", "https://old.example/token"),
        )
    decrypt.assert_not_called()
