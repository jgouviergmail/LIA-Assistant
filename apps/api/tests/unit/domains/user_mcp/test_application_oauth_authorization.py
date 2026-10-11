"""Linked consent must reach the original flow without changing its approved row."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.exceptions import AuthorizationError
from src.domains.user_mcp.authorization import initiate_personal_mcp_authorization


@pytest.mark.parametrize("refused", [False, True])
async def test_application_flow_forwards_fresh_guard_and_keeps_snapshot(monkeypatch, refused):
    db, owner, server_id, command_id = AsyncMock(), uuid4(), uuid4(), uuid4()
    service = MagicMock()
    service.get_with_ownership_check = AsyncMock(
        return_value=SimpleNamespace(
            auth_type="oauth2", url="https://example.org/mcp", oauth_metadata=None
        )
    )
    service.get_decrypted_credentials.return_value = {}
    service.cache_oauth_metadata = AsyncMock()
    check = AsyncMock()
    handler = AsyncMock()
    handler.initiate_flow.return_value = ("https://example.org/authorize", {"issuer": "issuer"})
    if refused:
        handler.initiate_flow.side_effect = AuthorizationError(detail={"error_code": "FORBIDDEN"})
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=handler)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "src.domains.user_mcp.authorization.UserMCPServerService", lambda _: service
    )
    monkeypatch.setattr("src.domains.user_mcp.authorization.MCPOAuthFlowHandler", lambda: context)
    arguments = {"application_command_id": command_id, "application_check": check}
    if refused:
        with pytest.raises(AuthorizationError):
            await initiate_personal_mcp_authorization(db, owner, server_id, **arguments)
    else:
        result = await initiate_personal_mcp_authorization(db, owner, server_id, **arguments)
        assert result.authorization_url == "https://example.org/authorize"
    assert handler.initiate_flow.call_args.kwargs["application_command_id"] == command_id
    assert handler.initiate_flow.call_args.kwargs["application_check"] is check
    service.cache_oauth_metadata.assert_not_awaited()
    db.commit.assert_not_awaited()
