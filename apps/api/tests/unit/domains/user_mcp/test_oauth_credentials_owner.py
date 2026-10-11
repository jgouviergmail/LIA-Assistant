"""Both legacy callbacks and approved writers reuse one guarded persistence owner."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.exceptions import AuthorizationError
from src.domains.user_mcp.service import UserMCPServerService


async def test_owned_oauth_write_refuses_fresh_guard_before_persistence():
    service = UserMCPServerService(AsyncMock())
    owner, server_id = uuid4(), uuid4()
    row = SimpleNamespace(id=server_id, user_id=owner)
    service.get_with_ownership_check = AsyncMock(return_value=row)
    service.repository = AsyncMock()
    check = AsyncMock(side_effect=AuthorizationError())
    with pytest.raises(AuthorizationError):
        await service.set_owned_oauth_credentials(server_id, owner, "encrypted", before_write=check)
    check.assert_awaited_once_with(service.db)
    service.repository.update.assert_not_awaited()


async def test_owned_oauth_write_uses_original_ownership_and_status_contract():
    service = UserMCPServerService(AsyncMock())
    owner, server_id = uuid4(), uuid4()
    row = SimpleNamespace(id=server_id, user_id=owner)
    service.get_with_ownership_check = AsyncMock(return_value=row)
    service.repository = AsyncMock()
    check = AsyncMock()
    result = await service.set_owned_oauth_credentials(
        server_id, owner, "encrypted", before_write=check
    )
    assert result is row
    service.get_with_ownership_check.assert_awaited_once_with(server_id, owner)
    service.repository.update.assert_awaited_once_with(
        row, {"credentials_encrypted": "encrypted", "status": "active"}
    )
    service.db.commit.assert_not_awaited()


async def test_foreign_target_refuses_before_guard_or_write():
    service = UserMCPServerService(AsyncMock())
    service.get_with_ownership_check = AsyncMock(side_effect=AuthorizationError())
    service.repository = AsyncMock()
    check = AsyncMock()
    with pytest.raises(AuthorizationError):
        await service.set_owned_oauth_credentials(uuid4(), uuid4(), "encrypted", before_write=check)
    check.assert_not_awaited()
    service.repository.update.assert_not_awaited()


async def test_legacy_callback_keeps_its_own_session_and_shared_status_payload(monkeypatch):
    db = AsyncMock()
    repository = AsyncMock()
    server = SimpleNamespace(id=uuid4())
    repository.get_by_id.return_value = server

    @asynccontextmanager
    async def database():
        yield db

    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    monkeypatch.setattr(
        "src.domains.user_mcp.service.UserMCPServerRepository", lambda selected: repository
    )
    await UserMCPServerService.update_oauth_credentials(server.id, "encrypted")
    repository.get_by_id.assert_awaited_once_with(server.id)
    repository.update.assert_awaited_once_with(
        server, {"credentials_encrypted": "encrypted", "status": "active"}
    )
    db.commit.assert_not_awaited()
