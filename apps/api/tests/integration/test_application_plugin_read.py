"""Original settings and native plugin reads share an owner-safe constant-query projection."""

from uuid import UUID

import pytest
from sqlalchemy import event

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.plugin_read import read_plugins
from src.domains.agents.application.plugin_read_schemas import PluginReadInput
from src.domains.plugins.models import UserPlugin
from src.domains.plugins.projection import list_plugin_projection
from src.domains.user_mcp.models import UserMCPServer
from tests.integration.domains.skills.test_per_account_skill_names import _skill, _user

pytestmark = pytest.mark.integration


async def _plugin(db, owner: UUID, name: str) -> UserPlugin:
    row = UserPlugin(user_id=owner, name=name, spec_version="1.0.0", manifest={"private": "secret"})
    db.add(row)
    await db.flush()
    return row


@pytest.mark.parametrize("scenario", ["visible", "plugins_off", "tools_off", "revoked"])
async def test_plugin_projection_is_owned_bounded_and_shared(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", scenario != "tools_off")
    monkeypatch.setattr(settings, "plugins_enabled", scenario != "plugins_off")
    owner = test_user.id
    foreign = await _user(async_session)
    rows = [await _plugin(async_session, owner, f"plugin-{i}") for i in range(3)]
    other = await _plugin(async_session, foreign, "foreign-plugin")
    own_skill = await _skill(async_session, "my-skill", owner)
    own_skill.plugin_id = rows[0].id
    foreign_skill = await _skill(async_session, "foreign-skill", foreign)
    foreign_skill.plugin_id = rows[0].id
    async_session.add_all(
        [
            UserMCPServer(
                user_id=owner, name="my-server", url="https://example.com", plugin_id=rows[0].id
            ),
            UserMCPServer(
                user_id=foreign,
                name="foreign-server",
                url="https://example.com",
                plugin_id=rows[0].id,
            ),
        ]
    )
    if scenario == "revoked":
        test_user.is_active = False
    await async_session.flush()
    if scenario != "visible":
        with pytest.raises(BaseAPIException):
            await read_plugins(async_session, owner, PluginReadInput())
        return
    queries: list[str] = []
    connection = await async_session.connection()

    def observe(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(connection.sync_connection, "before_cursor_execute", observe)
    try:
        original = await list_plugin_projection(async_session, owner)
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", observe)
    assert len(queries) == 3, "plugin count must not add component queries"
    result = await read_plugins(async_session, owner, PluginReadInput(limit=1))
    assert result.total == 3 and result.next_offset == 1
    assert result.items[0].model_dump() == original.plugins[0].model_dump()
    assert result.items[0].skill_names == ["my-skill"]
    assert result.items[0].server_names == ["my-server"]
    second = await read_plugins(async_session, owner, PluginReadInput(offset=1))
    assert {item.id for item in (*result.items, *second.items)} == {row.id for row in rows}
    assert other.id not in {item.id for item in second.items}
    raw = result.model_dump_json() + second.model_dump_json()
    assert all(
        secret not in raw
        for secret in ["secret", "manifest", "foreign-skill", "foreign-server", "https://"]
    )
