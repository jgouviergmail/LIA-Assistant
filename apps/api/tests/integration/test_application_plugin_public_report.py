"""A native receipt retains original issue taxonomy without re-serving source debug values."""

import io
import json
from pathlib import Path
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.plugin_url_import import (
    execute_plugin_url_import,
    prepare_plugin_url_import,
)
from src.domains.agents.application.plugin_url_import_schemas import PluginUrlImportInput
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.helpers.committed_account_session import async_session as async_session
from tests.integration.test_application_plugin_url_import import _package

pytestmark = pytest.mark.integration


async def test_native_import_report_never_exposes_original_debug_details(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for key in ("application_tools_enabled", "plugins_enabled", "skills_url_import_enabled"):
        monkeypatch.setattr(settings, key, True)
    monkeypatch.setattr(settings, "plugins_users_path", str(tmp_path / "plugins"))
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path / "skills"))
    owner = test_user.id
    await async_session.commit()
    content = io.BytesIO(_package())
    private = "PRIVATE_SOURCE_SCHEMA_DEBUG_VALUE"
    with ZipFile(content, "a") as archive:
        archive.writestr("mcp.json", json.dumps({"$schema": private, "mcpServers": {}}))
    monkeypatch.setattr(
        "src.domains.agents.application.plugin_url_import.fetch_skill_from_url",
        AsyncMock(return_value=(content.getvalue(), "native.zip")),
    )
    monkeypatch.setattr(
        "src.domains.agents.application.plugin_url_import.rate_limit_url_import", AsyncMock()
    )
    draft = await prepare_plugin_url_import(
        async_session, owner, PluginUrlImportInput(url="https://source.example/package.zip")
    )
    assert private not in draft.model_dump_json()
    receipt = PreferenceWriteReceipt()
    await execute_plugin_url_import(async_session, owner, draft, receipt)
    assert receipt.committed and receipt.values is not None
    assert private not in json.dumps(receipt.values)
    imported = receipt.values["plugin_url_import"]
    assert isinstance(imported, dict)
    warnings = imported["warnings"]
    assert isinstance(warnings, list) and isinstance(warnings[0], dict)
    assert warnings[0]["code"] == "mcp_schema_unsupported"
    assert warnings[0]["detail"] is None
