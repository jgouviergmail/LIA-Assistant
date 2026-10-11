"""Personal MCP reads share the UI metadata without exposing cached secrets."""

from contextlib import asynccontextmanager

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import event

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.core.security.utils import encrypt_data
from src.domains.agents.application.personal_mcp_read import read_personal_mcp
from src.domains.agents.application.personal_mcp_read_schemas import PersonalMCPReadInput
from src.domains.agents.tools import application_personal_mcp_tools
from src.domains.plugins.models import UserPlugin
from src.domains.user_mcp.management_projection import read_personal_mcp_metadata
from src.domains.user_mcp.models import UserMCPServer
from src.domains.user_mcp.projection import server_to_response
from src.domains.user_mcp.service import UserMCPServerService
from src.infrastructure.mcp.personal_metadata_gateway import configure_personal_mcp_metadata
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime
from tests.integration.domains.skills.test_per_account_skill_names import _user

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def metadata_owner():
    previous = configure_personal_mcp_metadata(read_personal_mcp_metadata)
    try:
        yield
    finally:
        configure_personal_mcp_metadata(previous)


@pytest.mark.parametrize(
    "scenario", ["visible", "foreign", "mcp_off", "personal_off", "tools_off", "revoked"]
)
async def test_personal_mcp_metadata_is_owned_bounded_private_and_shared(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", scenario != "tools_off")
    monkeypatch.setattr(settings, "mcp_enabled", scenario != "mcp_off")
    monkeypatch.setattr(settings, "mcp_user_enabled", scenario != "personal_off")
    owner = test_user.id
    foreign = await _user(async_session)
    plugin = UserPlugin(user_id=owner, name="owned-plugin", spec_version="1.0.0", manifest={})
    async_session.add(plugin)
    await async_session.flush()
    rows = [
        UserMCPServer(
            user_id=owner,
            name=f"server-{index}",
            url="https://example.com/private-token?key=private-secret",
            plugin_id=plugin.id,
            auth_type="api_key",
            status="error",
            is_enabled=True,
            credentials_encrypted=encrypt_data(
                '{"header_name":"X-Key","api_key":"private-secret"}'
            ),
            last_error="Authorization: Bearer private-secret",
            discovered_tools_cache=[
                {
                    "name": f"tool-{n}",
                    "description": "Display text",
                    "input_schema": {"default": "private-secret"},
                    "title": "My tool",
                }
                for n in range(3)
            ],
        )
        for index in range(3)
    ]
    other = UserMCPServer(user_id=foreign, name="foreign-server", url="https://foreign.example.com")
    async_session.add_all([*rows, other])
    if scenario == "revoked":
        test_user.is_active = False
    await async_session.flush()
    query = (
        PersonalMCPReadInput(server_id=other.id)
        if scenario == "foreign"
        else PersonalMCPReadInput(limit=1, tools_limit=1)
    )
    if scenario != "visible":
        with pytest.raises(BaseAPIException):
            await read_personal_mcp(async_session, owner, query)
        return
    statements = []
    connection = await async_session.connection()

    def observe(conn, cursor, statement, parameters, context, executemany):
        if "user_mcp_servers" in statement:
            statements.append(statement)

    event.listen(connection.sync_connection, "before_cursor_execute", observe)
    try:
        page = await read_personal_mcp(async_session, owner, query)
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", observe)
    assert len(statements) == 1
    assert page.total == 3 and page.next_offset == 1
    item = page.items[0]
    original = server_to_response(rows[0], UserMCPServerService(async_session))
    assert item.id == original.id and item.plugin_id == plugin.id == original.plugin_id
    assert item.endpoint_host == "example.com" and item.has_connection_error
    assert item.has_credentials and item.header_name == "X-Key"
    assert item.tool_count == 3 and len(item.tools) == 1 and item.next_tool_offset == 1
    assert item.tools[0].title == original.tools[0].title
    second = await read_personal_mcp(async_session, owner, PersonalMCPReadInput(offset=1))
    assert {entry.id for entry in (*page.items, *second.items)} == {row.id for row in rows}
    details = await read_personal_mcp(
        async_session, owner, PersonalMCPReadInput(server_id=item.id, tools_offset=1)
    )
    assert [tool.tool_name for tool in details.items[0].tools] == ["tool-1", "tool-2"]
    raw = page.model_dump_json() + second.model_dump_json()
    assert all(
        secret not in raw
        for secret in [
            "private-secret",
            "private-token",
            "input_schema",
            "foreign-server",
            "credentials_encrypted",
        ]
    )


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize(
    "scenario", ["normal", "off", "oversized", "malformed_private_schema", "empty_page"]
)
async def test_personal_mcp_real_tool_wrapper_has_finite_safe_results(
    async_session, test_user, monkeypatch, mode, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", scenario != "off")
    monkeypatch.setattr(settings, "mcp_enabled", True)
    monkeypatch.setattr(settings, "mcp_user_enabled", True)
    owner = test_user.id
    row = UserMCPServer(
        user_id=owner,
        name="visible-server",
        url="https://example.com/secret?token=secret",
        domain_description="x" * 70_000 if scenario == "oversized" else "Visible description",
        discovered_tools_cache=[
            {
                "name": "visible-tool",
                "description": "visible",
                "input_schema": "private malformed data",
            }
        ],
    )
    async_session.add(row)
    await async_session.flush()

    @asynccontextmanager
    async def database():
        yield async_session

    monkeypatch.setattr(application_personal_mcp_tools, "get_db_context", database)
    with installed_runtime_context(user_id=owner, deps=object(), execution_mode=mode):
        result = await application_personal_mcp_tools.get_lia_personal_mcp_servers_tool.coroutine(
            query={"offset": 100} if scenario == "empty_page" else {},
            runtime=make_tool_runtime(user_id=owner, execution_mode=mode, store=InMemoryStore()),
        )
    assert result.success == (scenario not in {"off", "oversized"})
    if result.success:
        data = result.structured_data
        assert data["total"] == 1
        if scenario == "empty_page":
            assert data["items"] == [] and data["next_offset"] is None
        else:
            assert data["items"][0]["name"] == row.name
        assert "secret" not in str(data) and "private malformed data" not in str(data)
    else:
        assert result.error_code == (
            "CAPABILITY_DISABLED" if scenario == "off" else "INVALID_INPUT"
        )
