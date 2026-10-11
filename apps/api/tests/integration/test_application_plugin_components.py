"""Late MCP edits and authority refusal cannot be hidden by a multi-component import."""

import io
import json
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import AGENT_PLUGINS_MCP_SCHEMA_ID
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.plugin_url_import import (
    execute_plugin_url_import,
    prepare_plugin_url_import,
)
from src.domains.agents.application.plugin_url_import_schemas import PluginUrlImportInput
from src.domains.user_mcp.models import UserMCPServer
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.domains.skills.test_per_account_skill_names import _user
from tests.integration.test_application_plugin_read import _plugin
from tests.integration.test_application_plugin_url_import import _package

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["success", "late_edit", "partial_refusal"])
async def test_native_plugin_components_compare_after_dns_and_retain_partial_commit_truth(
    async_engine, monkeypatch, tmp_path, scenario
):
    # A second independent transaction must see committed data: savepoint-bound
    # fixture sessions cannot simulate another request's durable edit.
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        owner = await _user(db)
        await db.commit()
        try:
            await _component_case(db, owner, monkeypatch, tmp_path, scenario)
        finally:
            await db.rollback()
            user = await db.get(User, owner)
            await db.delete(user)
            await db.commit()


async def _component_case(async_session, owner, monkeypatch, tmp_path, scenario):
    for key in (
        "application_tools_enabled",
        "plugins_enabled",
        "skills_url_import_enabled",
        "skills_enabled",
        "mcp_enabled",
    ):
        monkeypatch.setattr(settings, key, True)
    monkeypatch.setattr(settings, "plugins_users_path", str(tmp_path / "plugins"))
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path / "skills"))
    monkeypatch.setattr("src.domains.skills.cache.SkillsCache.invalidate_and_reload", AsyncMock())
    monkeypatch.setattr(
        "src.domains.user_mcp.service.UserMCPServerService._disconnect_from_pool", AsyncMock()
    )
    plugin = await _plugin(async_session, owner, "native-plugin")
    plugin_id = plugin.id
    server = UserMCPServer(
        user_id=owner,
        name="native-plugin:api",
        plugin_id=plugin_id,
        url="https://old.example/mcp",
        extra_headers={"X-Version": "old"},
        credentials_encrypted="preserved-private-credential",
    )
    async_session.add(server)
    await async_session.commit()
    server_id = server.id
    content = io.BytesIO(_package(skills=scenario == "partial_refusal"))
    with ZipFile(content, "a") as archive:
        archive.writestr(
            "mcp.json",
            json.dumps(
                {
                    "$schema": AGENT_PLUGINS_MCP_SCHEMA_ID,
                    "mcpServers": {
                        "api": {
                            "type": "streamable-http",
                            "url": "https://new.example/mcp",
                            "headers": {"X-Version": "new"},
                        }
                    },
                }
            ),
        )
    monkeypatch.setattr(
        "src.domains.agents.application.plugin_url_import.fetch_skill_from_url",
        AsyncMock(return_value=(content.getvalue(), "native.zip")),
    )
    monkeypatch.setattr(
        "src.domains.agents.application.plugin_url_import.rate_limit_url_import", AsyncMock()
    )
    draft = await prepare_plugin_url_import(
        async_session,
        owner,
        PluginUrlImportInput(
            url="https://source.example/plugin.zip",
            replace_plugin_id=plugin_id,
        ),
    )
    assert "preserved-private-credential" not in draft.model_dump_json()

    async def validate(_url):
        if scenario == "late_edit":
            async with AsyncSession(async_session.bind, expire_on_commit=False) as other:
                row = await other.get(UserMCPServer, server_id)
                row.url = "https://concurrent.example/mcp"
                await other.commit()
        elif scenario == "partial_refusal":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        return True, None

    monkeypatch.setattr("src.domains.user_mcp.service.validate_http_endpoint", validate)
    receipt = PreferenceWriteReceipt()
    if scenario == "success":
        await execute_plugin_url_import(async_session, owner, draft, receipt)
        assert receipt.committed
        await async_session.refresh(server)
        assert server.url == "https://new.example/mcp"
        assert server.extra_headers == {"X-Version": "new"}
        assert server.credentials_encrypted == "preserved-private-credential"
    else:
        with pytest.raises((CommandRejected, BaseAPIException)):
            await execute_plugin_url_import(async_session, owner, draft, receipt)
        if scenario == "late_edit":
            assert not receipt.committed
            await async_session.rollback()
            actual = await async_session.scalar(
                select(UserMCPServer).where(UserMCPServer.id == server_id)
            )
            assert actual.url == "https://concurrent.example/mcp"
            assert actual.extra_headers == {"X-Version": "old"}
        else:
            assert receipt.committed and receipt.values["plugin_url_import"]["complete"] is False
            assert receipt.values["plugin_url_import"]["installed_skill_names"] == ["my-skill"]
