"""A package update must refuse an inconsistent group before importing or dropping members."""

import io
import json
from zipfile import ZipFile

import pytest

from src.core.config import settings
from src.core.constants import AGENT_PLUGINS_PLUGIN_SCHEMA_ID
from src.core.exceptions import BaseAPIException
from src.domains.plugins.import_service import PluginImportService
from src.domains.user_mcp.models import UserMCPServer
from tests.integration.domains.skills.test_per_account_skill_names import _skill, _user
from tests.integration.test_application_plugin_read import _plugin

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("member", ["skill", "server"])
async def test_update_refuses_foreign_group_members_before_any_live_write(
    async_session, test_user, monkeypatch, tmp_path, member
):
    monkeypatch.setattr(settings, "plugins_users_path", str(tmp_path / "plugins"))
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path / "skills"))
    owner = test_user.id
    other = await _user(async_session)
    plugin = await _plugin(async_session, owner, "scope-update")
    skill = await _skill(async_session, "foreign-member", other if member == "skill" else owner)
    skill.plugin_id = plugin.id
    server = UserMCPServer(
        user_id=other if member == "server" else owner,
        name="member-api",
        url="https://example.com",
        plugin_id=plugin.id,
    )
    async_session.add(server)
    await async_session.flush()
    identity, version = plugin.id, plugin.version
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "plugin.json",
            json.dumps(
                {"$schema": AGENT_PLUGINS_PLUGIN_SCHEMA_ID, "name": plugin.name, "version": "new"}
            ),
        )
    with pytest.raises((BaseAPIException, ValueError)):
        await PluginImportService(async_session).import_upload(buffer.getvalue(), owner_id=owner)
    assert plugin.id == identity and plugin.version == version
    assert await async_session.get(type(skill), skill.id) is skill
    assert await async_session.get(type(server), server.id) is server
    assert not (tmp_path / "plugins").exists()
