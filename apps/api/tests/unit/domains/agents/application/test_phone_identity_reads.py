"""Phone identity reads require both current switches before any secret-bearing source access."""

from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.infrastructure.phone_identity import PhoneIdentityData, PhoneIdentityProjection

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("switch", ["application_tools_enabled", "telephony_enabled"])
async def test_disabled_switch_refuses_phone_source_access(
    monkeypatch: pytest.MonkeyPatch, switch: str
) -> None:
    module = import_module("src.domains.agents.application.phone_operations")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "telephony_enabled", True)
    monkeypatch.setattr(settings, switch, False)
    gateway = AsyncMock()
    monkeypatch.setattr(module, "get_phone_identity", lambda: gateway)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = None
    with pytest.raises(AuthorizationError):
        await module.read_phone_identity(db, uuid4())
    gateway.read.assert_not_awaited()


@pytest.mark.parametrize("switch", ["application_tools_enabled", "telephony_enabled"])
async def test_switch_revocation_during_phone_read_withholds_the_result(
    monkeypatch: pytest.MonkeyPatch, switch: str
) -> None:
    module = import_module("src.domains.agents.application.phone_operations")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "telephony_enabled", True)
    monkeypatch.setattr(module, "load_actor", AsyncMock())

    async def revoked(_db: AsyncSession, _actor: object) -> PhoneIdentityProjection:
        monkeypatch.setattr(settings, switch, False)
        return PhoneIdentityProjection(
            number_status="unset",
            identity=PhoneIdentityData(
                verified=False,
                disabled_domains=[],
                available_domains=[],
                rich_context_enabled=False,
                verification_pending=False,
                call_mode="direct",
                call_mode_effective="direct",
                live_available=False,
            ),
        )

    gateway = AsyncMock()
    gateway.read.side_effect = revoked
    monkeypatch.setattr(module, "get_phone_identity", lambda: gateway)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = None
    with pytest.raises(AuthorizationError):
        await module.read_phone_identity(db, uuid4())
    gateway.read.assert_awaited_once()


def test_phone_identity_read_has_no_credentials_or_verification_action_input() -> None:
    from src.core.application_tools import APPLICATION_TOOL_NAMES
    from src.domains.agents.application.catalogue_registration import APPLICATION_MANIFESTS
    from src.domains.agents.application.operation_spec import OperationKind
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS
    from src.domains.feature_switches.registry import PlatformCapability

    module = import_module("src.domains.agents.tools.application_phone_tools")
    assert not module.get_lia_phone_identity_tool.tool_call_schema.model_fields
    assert "get_lia_phone_identity_tool" in APPLICATION_TOOL_NAMES
    spec = APPLICATION_OPERATIONS.get("phone_identity.read")
    assert spec.sections == ("telephony-identity",)
    assert spec.kind == OperationKind.READ and spec.required_capabilities == (
        PlatformCapability.TELEPHONY,
    )
    manifest = next(row for row in APPLICATION_MANIFESTS if row.name == spec.tool_name)
    assert manifest.mutation_policy == "read"
