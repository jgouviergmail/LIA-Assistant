"""Every component is ownership-checked before the original group uninstall can act."""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.exceptions import BaseAPIException
from src.domains.plugins.group_scope import load_plugin_group
from src.domains.plugins.import_service import PluginImportService
from src.domains.user_mcp.models import UserMCPServer
from tests.integration.domains.skills.test_per_account_skill_names import _skill, _user
from tests.integration.test_application_plugin_read import _plugin

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("foreign", ["none", "skill", "server", "plugin"])
async def test_group_refuses_inconsistent_owner_before_disk_pool_or_sql_delete(
    async_session, test_user, foreign
):
    owner = test_user.id
    other = await _user(async_session)
    plugin = await _plugin(async_session, other if foreign == "plugin" else owner, "scope-test")
    skill = await _skill(async_session, "owned-component", other if foreign == "skill" else owner)
    skill.plugin_id = plugin.id
    server = UserMCPServer(
        user_id=other if foreign == "server" else owner,
        name="component-api",
        url="https://example.com",
        plugin_id=plugin.id,
    )
    async_session.add(server)
    await async_session.flush()
    with (
        patch("src.domains.plugins.import_service.asyncio.to_thread", AsyncMock()) as disk,
        patch(
            "src.domains.user_mcp.service.UserMCPServerService._disconnect_from_pool", AsyncMock()
        ) as pool,
    ):
        if foreign == "none":
            group = await load_plugin_group(async_session, owner, plugin.id)
            assert group.plugin.id == plugin.id
            assert [row.id for row in group.skills] == [skill.id]
            assert [row.id for row in group.servers] == [server.id]
        else:
            with pytest.raises((ValueError, BaseAPIException)):
                await PluginImportService(async_session).uninstall(plugin.id, owner_id=owner)
        disk.assert_not_awaited()
        pool.assert_not_awaited()
        assert await async_session.get(type(plugin), plugin.id) is plugin
