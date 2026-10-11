"""Fresh consent refusal precedes original OAuth credential purging."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import AuthorizationError
from src.core.security.utils import encrypt_data
from src.domains.user_mcp.service import UserMCPServerService


async def test_disconnect_oauth_checks_fresh_authority_before_purging():
    service = UserMCPServerService(AsyncMock())
    encrypted = encrypt_data(json.dumps({"client_id": "client", "access_token": "private"}))
    server = MagicMock(auth_type="oauth2", credentials_encrypted=encrypted)
    service.get_with_ownership_check = AsyncMock(return_value=server)
    service.repository = AsyncMock()
    service._disconnect_from_pool = AsyncMock()
    with pytest.raises(AuthorizationError):
        await service.disconnect_oauth(
            uuid4(), uuid4(), before_write=AsyncMock(side_effect=AuthorizationError())
        )
    service.repository.update.assert_not_awaited()
    service._disconnect_from_pool.assert_not_awaited()
    assert server.credentials_encrypted == encrypted


async def test_guarded_withdrawal_propagates_failed_pool_invalidation():
    service = UserMCPServerService(AsyncMock())
    server = MagicMock(
        auth_type="oauth2",
        credentials_encrypted=encrypt_data(json.dumps({"access_token": "private"})),
    )
    service.get_with_ownership_check = AsyncMock(return_value=server)
    service.repository = AsyncMock()
    service.repository.update.return_value = server
    pool = MagicMock(disconnect=AsyncMock(side_effect=RuntimeError("cache unavailable")))
    with patch("src.infrastructure.mcp.user_pool.get_user_mcp_pool", return_value=pool):
        with pytest.raises(RuntimeError, match="cache unavailable"):
            await service.disconnect_oauth(uuid4(), uuid4(), before_write=AsyncMock())
