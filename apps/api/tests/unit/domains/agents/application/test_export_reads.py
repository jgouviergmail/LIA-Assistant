"""Export management state can be read without creating or downloading an archive."""

from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError

pytestmark = pytest.mark.unit


async def test_disabled_application_tools_stop_export_state_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.agents.application.export_operations")
    monkeypatch.setattr(settings, "application_tools_enabled", False)
    read = AsyncMock()
    gateway = AsyncMock()
    gateway.read = read
    monkeypatch.setattr(module, "get_account_exports", lambda: gateway)
    with pytest.raises(AuthorizationError):
        await module.read_export_settings(AsyncMock(spec=AsyncSession), uuid4())
    read.assert_not_awaited()


async def test_operator_revocation_during_export_read_withholds_the_saved_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infrastructure.account_exports import AccountExportProjection

    module = import_module("src.domains.agents.application.export_operations")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(module, "load_actor", AsyncMock())

    async def revoked(_db: AsyncSession, _actor: object) -> AccountExportProjection:
        monkeypatch.setattr(settings, "application_tools_enabled", False)
        return AccountExportProjection(enabled=True, download_available=True)

    gateway = AsyncMock()
    gateway.read.side_effect = revoked
    monkeypatch.setattr(module, "get_account_exports", lambda: gateway)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = None
    with pytest.raises(AuthorizationError):
        await module.read_export_settings(db, uuid4())
    gateway.read.assert_awaited_once()


def test_export_tool_has_no_archive_creation_or_download_input() -> None:
    module = import_module("src.domains.agents.tools.application_export_tools")
    assert not module.get_lia_account_export_tool.tool_call_schema.model_fields


def test_export_read_has_one_registered_read_only_identity() -> None:
    from src.core.application_tools import APPLICATION_TOOL_NAMES
    from src.domains.agents.application.catalogue_registration import APPLICATION_MANIFESTS
    from src.domains.agents.application.operation_spec import OperationKind
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS

    assert "get_lia_account_export_tool" in APPLICATION_TOOL_NAMES
    spec = APPLICATION_OPERATIONS.get("account_export.read")
    assert spec.kind == OperationKind.READ
    manifest = next(row for row in APPLICATION_MANIFESTS if row.name == spec.tool_name)
    assert manifest.mutation_policy == "read"
