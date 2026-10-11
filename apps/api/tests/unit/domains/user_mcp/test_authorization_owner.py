"""Authorization reuses the original flow while exposing fresh owner guards."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import AuthorizationError, BadGatewayError, ValidationError
from src.domains.user_mcp.authorization import initiate_personal_mcp_authorization


@pytest.mark.parametrize("refuse_at", [None, "flow", "write"])
async def test_authorization_checks_before_network_and_metadata_write(refuse_at):
    db = AsyncMock()
    owner, server_id = uuid4(), uuid4()
    server = SimpleNamespace(
        id=server_id,
        user_id=owner,
        auth_type="oauth2",
        url="https://example.org/mcp",
        oauth_metadata={"requested_scopes": "read"},
    )
    service = MagicMock()
    service.get_with_ownership_check = AsyncMock(return_value=server)
    service.get_decrypted_credentials.return_value = {
        "client_id": "client",
        "client_secret": "private",
        "issuer": "https://issuer.example.org",
    }
    service.cache_oauth_metadata = AsyncMock()
    handler = AsyncMock()
    handler.initiate_flow.return_value = (
        "https://issuer.example.org/authorize?state=private",
        {"issuer": "https://issuer.example.org"},
    )
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=handler)
    context.__aexit__ = AsyncMock(return_value=False)
    before_flow = AsyncMock(side_effect=AuthorizationError() if refuse_at == "flow" else None)
    before_write = AsyncMock(side_effect=AuthorizationError() if refuse_at == "write" else None)
    with (
        patch("src.domains.user_mcp.authorization.UserMCPServerService", return_value=service),
        patch("src.domains.user_mcp.authorization.MCPOAuthFlowHandler", return_value=context),
    ):
        if refuse_at:
            with pytest.raises(AuthorizationError):
                await initiate_personal_mcp_authorization(
                    db, owner, server_id, before_flow=before_flow, before_write=before_write
                )
        else:
            result = await initiate_personal_mcp_authorization(
                db, owner, server_id, before_flow=before_flow, before_write=before_write
            )
            assert result.authorization_url.startswith("https://issuer.example.org/")
            handler.initiate_flow.assert_awaited_once_with(
                server_id=server_id,
                user_id=owner,
                mcp_url=server.url,
                cached_metadata=server.oauth_metadata,
                client_id="client",
                client_secret="private",
                requested_scopes="read",
                stored_issuer="https://issuer.example.org",
            )
    assert handler.initiate_flow.await_count == int(refuse_at != "flow")
    assert service.cache_oauth_metadata.await_count == int(refuse_at is None)
    assert db.commit.await_count == int(refuse_at is None)


async def test_malformed_stored_client_refuses_without_exposing_its_secret():
    service = MagicMock()
    service.get_with_ownership_check = AsyncMock(
        return_value=SimpleNamespace(
            auth_type="oauth2", oauth_metadata=None, url="https://example.org/mcp"
        )
    )
    service.get_decrypted_credentials.return_value = {
        "client_id": ["invalid"],
        "client_secret": "private-client-secret",
    }
    with (
        patch("src.domains.user_mcp.authorization.UserMCPServerService", return_value=service),
        patch("src.domains.user_mcp.authorization.MCPOAuthFlowHandler") as handler,
    ):
        with pytest.raises(ValidationError) as failure:
            await initiate_personal_mcp_authorization(AsyncMock(), uuid4(), uuid4())
    assert "private" not in str(failure.value)
    handler.assert_not_called()


async def test_provider_error_is_sanitized_and_never_written_or_logged_as_text():
    service = MagicMock()
    service.get_with_ownership_check = AsyncMock(
        return_value=SimpleNamespace(
            auth_type="oauth2", oauth_metadata=None, url="https://example.org/mcp"
        )
    )
    service.get_decrypted_credentials.return_value = {}
    service.cache_oauth_metadata = AsyncMock()
    handler = AsyncMock()
    handler.initiate_flow.side_effect = RuntimeError("private-provider-secret")
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=handler)
    context.__aexit__ = AsyncMock(return_value=False)
    db = AsyncMock()
    with (
        patch("src.domains.user_mcp.authorization.UserMCPServerService", return_value=service),
        patch("src.domains.user_mcp.authorization.MCPOAuthFlowHandler", return_value=context),
        patch("src.domains.user_mcp.authorization.logger") as logger,
    ):
        with pytest.raises(BadGatewayError) as failure:
            await initiate_personal_mcp_authorization(db, uuid4(), uuid4())
    assert "private" not in str(failure.value) + str(logger.error.call_args)
    service.cache_oauth_metadata.assert_not_awaited()
    db.commit.assert_not_awaited()
