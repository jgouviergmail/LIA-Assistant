"""A package update uses the same SSRF gate and reconnect seam as the original MCP menu."""

import io
import json
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest

from src.core.config import settings
from src.core.constants import AGENT_PLUGINS_MCP_SCHEMA_ID, AGENT_PLUGINS_PLUGIN_SCHEMA_ID
from src.domains.plugins.import_service import PluginImportService
from src.domains.plugins.schemas import PluginComponentStatus
from src.domains.user_mcp.models import UserMCPServer
from src.domains.user_mcp.service import UserMCPServerService
from tests.integration.test_application_plugin_read import _plugin

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("allowed", [False, True])
async def test_plugin_endpoint_update_revalidates_before_replacing_endpoint_or_headers(
    async_session, test_user, monkeypatch, tmp_path, allowed
):
    monkeypatch.setattr(settings, "plugins_users_path", str(tmp_path / "plugins"))
    plugin = await _plugin(async_session, test_user.id, "endpoint-update")
    server = UserMCPServer(
        user_id=test_user.id,
        name=f"{plugin.name}:api",
        url="https://old.example/mcp",
        plugin_id=plugin.id,
        extra_headers={"X-Version": "old"},
        credentials_encrypted="unchanged-encrypted-value",
    )
    async_session.add(server)
    await async_session.flush()
    validate = AsyncMock(return_value=(allowed, None if allowed else "private address"))
    disconnect = AsyncMock()
    monkeypatch.setattr("src.domains.user_mcp.service.validate_http_endpoint", validate)
    monkeypatch.setattr(UserMCPServerService, "_disconnect_from_pool", disconnect)
    buffer = io.BytesIO()
    endpoint = "https://new.example/mcp"
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "plugin.json",
            json.dumps({"$schema": AGENT_PLUGINS_PLUGIN_SCHEMA_ID, "name": plugin.name}),
        )
        archive.writestr(
            "mcp.json",
            json.dumps(
                {
                    "$schema": AGENT_PLUGINS_MCP_SCHEMA_ID,
                    "mcpServers": {
                        "api": {
                            "type": "streamable-http",
                            "url": endpoint,
                            "headers": {"X-Version": "new"},
                        }
                    },
                }
            ),
        )
    report = await PluginImportService(async_session).import_upload(
        buffer.getvalue(), owner_id=test_user.id
    )
    validate.assert_awaited_once_with(endpoint)
    component = next(item for item in report.components if item.key == "api")
    assert server.credentials_encrypted == "unchanged-encrypted-value"
    if allowed:
        assert component.status is PluginComponentStatus.UPDATED
        assert server.url == endpoint and server.extra_headers == {"X-Version": "new"}
        disconnect.assert_awaited_once_with(test_user.id, server.id)
    else:
        assert component.status is PluginComponentStatus.SKIPPED
        assert server.url == "https://old.example/mcp" and server.extra_headers == {
            "X-Version": "old"
        }
        disconnect.assert_not_awaited()
