"""Actual row locks prevent old clients restoring revoked or replaced OAuth state."""

import json
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.user_mcp.models import UserMCPServer
from src.domains.user_mcp.oauth_refresh import persist_matching_oauth_refresh

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "mutation", ["none", "authorization", "disconnect", "endpoint", "url", "owner"]
)
@pytest.mark.parametrize("invalid_grant", [False, True])
async def test_delayed_refresh_cannot_overwrite_newer_state(
    async_session, test_user, monkeypatch, mutation, invalid_grant
):
    old = {"access_token": "old-token", "refresh_token": "old-refresh", "client_id": "client"}
    row = UserMCPServer(
        user_id=test_user.id,
        name="refresh target",
        url="https://example.org/mcp",
        auth_type="oauth2",
        status="active",
        credentials_encrypted=encrypt_data(json.dumps(old)),
        oauth_metadata={"token_endpoint": "https://example.org/token"},
    )
    async_session.add(row)
    await async_session.commit()
    owner, server_id = test_user.id, row.id
    if mutation == "authorization":
        row.credentials_encrypted = encrypt_data(json.dumps({"access_token": "new-authorization"}))
    if mutation == "disconnect":
        row.status = "auth_required"
    if mutation == "endpoint":
        row.oauth_metadata = {"token_endpoint": "https://other.example/token"}
    if mutation == "url":
        row.url = "https://other.example/mcp"
    await async_session.commit()
    before = (row.credentials_encrypted, row.status)

    @asynccontextmanager
    async def database():
        yield async_session
        await async_session.commit()

    monkeypatch.setattr("src.domains.user_mcp.oauth_refresh.get_db_context", database)
    replacement = None if invalid_grant else {**old, "access_token": "rotated-token"}
    saved = await persist_matching_oauth_refresh(
        server_id,
        uuid4() if mutation == "owner" else owner,
        "https://example.org/token",
        "https://example.org/mcp",
        old,
        replacement,
    )
    await async_session.refresh(row)
    assert saved == (mutation == "none")
    if mutation != "none":
        assert (row.credentials_encrypted, row.status) == before
    elif invalid_grant:
        assert row.status == "auth_required"
    else:
        assert (
            json.loads(decrypt_data(row.credentials_encrypted))["access_token"] == "rotated-token"
        )
