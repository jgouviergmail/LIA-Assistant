"""Probe writes must never swallow a fresh confirmation/authority refusal."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import AuthorizationError
from src.domains.user_mcp.models import UserMCPAuthType
from src.domains.user_mcp.service import UserMCPServerService


@pytest.mark.parametrize("connection_fails", [False, True])
async def test_late_refusal_does_not_write_success_or_error(connection_fails: bool) -> None:
    db = AsyncMock()
    service = UserMCPServerService(db)
    service.repository = AsyncMock()
    owner_id, server_id = uuid4(), uuid4()
    server = SimpleNamespace(
        id=server_id,
        user_id=owner_id,
        name="Calendar",
        url="https://example.org/mcp",
        auth_type=UserMCPAuthType.NONE.value,
        credentials_encrypted=None,
        timeout_seconds=30,
        extra_headers=None,
        domain_description="Existing",
    )
    service.get_with_ownership_check = AsyncMock(return_value=server)
    pool = SimpleNamespace(
        get_or_connect=AsyncMock(
            side_effect=TimeoutError("private") if connection_fails else None,
            return_value=SimpleNamespace(tools=[]),
        )
    )
    before_connect = AsyncMock()
    before_write = AsyncMock(side_effect=AuthorizationError())
    with (
        patch("src.infrastructure.mcp.user_pool.get_user_mcp_pool", return_value=pool),
        patch("src.infrastructure.mcp.auth.build_auth_for_server", return_value=MagicMock()),
        patch(
            "src.domains.agents.services.tool_selector.compute_tool_embeddings",
            AsyncMock(return_value={}),
        ),
    ):
        with pytest.raises(AuthorizationError):
            await service.test_connection(
                server_id, owner_id, before_connect=before_connect, before_write=before_write
            )
    before_connect.assert_awaited_once_with(db)
    pool.get_or_connect.assert_awaited_once()
    before_write.assert_awaited_once_with(db)
    service.repository.update.assert_not_awaited()


async def test_preflight_refusal_does_not_contact_server() -> None:
    service = UserMCPServerService(AsyncMock())
    service.get_with_ownership_check = AsyncMock(return_value=MagicMock())
    pool = SimpleNamespace(get_or_connect=AsyncMock())
    with patch("src.infrastructure.mcp.user_pool.get_user_mcp_pool", return_value=pool):
        with pytest.raises(AuthorizationError):
            await service.test_connection(
                uuid4(), uuid4(), before_connect=AsyncMock(side_effect=AuthorizationError())
            )
    pool.get_or_connect.assert_not_awaited()


async def test_confirmed_probe_does_not_report_a_failed_write_as_success() -> None:
    service = UserMCPServerService(AsyncMock())
    server = MagicMock(domain_description="Existing")
    service.get_with_ownership_check = AsyncMock(return_value=server)
    service.repository = AsyncMock()
    service.repository.update.side_effect = RuntimeError("storage unavailable")
    pool = SimpleNamespace(get_or_connect=AsyncMock(return_value=SimpleNamespace(tools=[])))
    with (
        patch("src.infrastructure.mcp.user_pool.get_user_mcp_pool", return_value=pool),
        patch("src.infrastructure.mcp.auth.build_auth_for_server", return_value=MagicMock()),
        patch(
            "src.domains.agents.services.tool_selector.compute_tool_embeddings",
            AsyncMock(return_value={}),
        ),
    ):
        with pytest.raises(RuntimeError, match="storage unavailable"):
            await service.test_connection(uuid4(), uuid4(), before_write=AsyncMock())


async def test_probe_failure_logs_type_without_provider_secret() -> None:
    service = UserMCPServerService(AsyncMock())
    service.get_with_ownership_check = AsyncMock(
        return_value=MagicMock(domain_description="Existing", auth_type="none")
    )
    service.repository = AsyncMock()
    pool = SimpleNamespace(get_or_connect=AsyncMock(side_effect=TimeoutError("private-api-key")))
    with (
        patch("src.infrastructure.mcp.user_pool.get_user_mcp_pool", return_value=pool),
        patch("src.infrastructure.mcp.auth.build_auth_for_server", return_value=MagicMock()),
        patch("src.domains.user_mcp.service.logger") as log,
    ):
        result = await service.test_connection(uuid4(), uuid4(), before_write=AsyncMock())
    assert not result["success"]
    assert log.warning.call_args.kwargs["error_type"] == "TimeoutError"
    assert "private-api-key" not in repr(log.warning.call_args)
    assert "private-api-key" not in repr(result)
