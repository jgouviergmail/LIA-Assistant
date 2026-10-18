"""An internal offline install never weakens the public credential validator."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ValidationError as APIValidationError
from src.domains.user_mcp.installation import OfflineMCPInstallation
from src.domains.user_mcp.models import UserMCPAuthType, UserMCPServer
from src.domains.user_mcp.schemas import UserMCPServerCreate
from src.domains.user_mcp.service import UserMCPServerService


@pytest.mark.parametrize("auth_type", list(UserMCPAuthType))
async def test_shared_server_is_disabled_and_has_no_credentials_at_creation(
    auth_type: UserMCPAuthType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = UserMCPServerService(MagicMock(spec=AsyncSession))
    monkeypatch.setattr(service, "_check_creation_constraints", AsyncMock())
    monkeypatch.setattr(
        "src.domains.user_mcp.service.validate_http_endpoint",
        AsyncMock(return_value=(True, None)),
    )
    monkeypatch.setattr(service.repository, "lock_owner_for_creation", AsyncMock())
    captured: list[dict[str, object]] = []

    async def create(values: dict[str, object]) -> UserMCPServer:
        captured.append(values)
        return UserMCPServer(**values)

    monkeypatch.setattr(service.repository, "create", create)
    server = await service.create_server(
        uuid4(),
        UserMCPServerCreate(name="Received", url="https://example.com/mcp"),
        offline_install=OfflineMCPInstallation(auth_type=auth_type, header_name="X-Service-Key"),
    )
    assert server.is_enabled is False
    assert captured[0]["is_enabled"] is False
    assert captured[0]["credentials_encrypted"] is None
    assert captured[0]["hitl_required"] is None
    assert captured[0]["auth_type"] == auth_type.value
    assert server.status == ("inactive" if auth_type is UserMCPAuthType.NONE else "auth_required")
    assert service.build_response_metadata(server)["has_credentials"] is False
    if auth_type is UserMCPAuthType.API_KEY:
        assert service.build_response_metadata(server)["header_name"] == "X-Service-Key"


@pytest.mark.parametrize("auth_type", [UserMCPAuthType.API_KEY, UserMCPAuthType.BEARER])
def test_public_creation_still_requires_the_selected_credential(
    auth_type: UserMCPAuthType,
) -> None:
    with pytest.raises(ValidationError):
        UserMCPServerCreate(name="Public", url="https://example.com/mcp", auth_type=auth_type)


@pytest.mark.parametrize("status", ["inactive", "auth_required", "error"])
async def test_enable_requires_readiness_but_disable_remains_available(
    status: str,
) -> None:
    db = MagicMock(spec=AsyncSession)
    service = UserMCPServerService(db)
    server = UserMCPServer(
        id=uuid4(),
        user_id=uuid4(),
        name="Received",
        url="https://example.com/mcp",
        auth_type="api_key",
        is_enabled=False,
        status=status,
    )
    service.repository.get_by_id = AsyncMock(return_value=server)
    service.repository.update = AsyncMock(return_value=server)
    service._disconnect_from_pool = AsyncMock()
    with pytest.raises(APIValidationError):
        await service.toggle_server(server.id, server.user_id, enabled=True)
    service.repository.update.assert_not_awaited()
    await service.toggle_server(server.id, server.user_id, enabled=False)
    service.repository.update.assert_awaited_once()
