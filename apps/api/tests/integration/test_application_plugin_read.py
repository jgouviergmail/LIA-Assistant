"""Original settings and native plugin reads share an owner-safe constant-query projection."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.plugin_read import read_plugins
from src.domains.agents.application.plugin_read_schemas import PluginReadInput
from src.domains.peers.capability_models import PeerCapabilityComponent, PeerCapabilityTransfer
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


@pytest.mark.parametrize(
    "scenario,plugin_count",
    [
        ("visible", 1),
        ("visible", 3),
        ("visible", 12),
        ("plugins_off", 3),
        ("tools_off", 3),
        ("revoked", 3),
    ],
)
async def test_plugin_projection_is_owned_bounded_and_shared(
    async_session, test_user, monkeypatch, scenario, plugin_count
):
    monkeypatch.setattr(settings, "application_tools_enabled", scenario != "tools_off")
    monkeypatch.setattr(settings, "plugins_enabled", scenario != "plugins_off")
    owner = test_user.id
    foreign = await _user(async_session)
    rows = [await _plugin(async_session, owner, f"plugin-{i:02}") for i in range(plugin_count)]
    other = await _plugin(async_session, foreign, "foreign-plugin")
    shared_at = datetime.now(UTC)
    sender = await async_session.get(type(test_user), foreign)
    sender.full_name = "Private sender"
    receipt = PeerCapabilityTransfer(
        sender_id=foreign,
        recipient_id=owner,
        source_id=other.id,
        idempotency_key=uuid4(),
        kind="plugin",
        name=rows[0].name,
        digest="1" * 64,
        status="installed",
        expires_at=shared_at + timedelta(minutes=5),
        transferred_at=shared_at,
    )
    async_session.add(receipt)
    await async_session.flush()
    async_session.add(
        PeerCapabilityComponent(
            transfer_id=receipt.id,
            kind="plugin",
            key=rows[0].name,
            resource_id=rows[0].id,
            fingerprint="1" * 64,
            installed=True,
        )
    )
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
    # Three component queries plus ONE batched origin lookup, at every list size.
    assert len(queries) == 4, "plugin count must not add component or origin queries"
    assert original.plugins[0].shared_origin.sender_display_name == "Private sender"
    result = await read_plugins(async_session, owner, PluginReadInput(limit=1))
    assert result.total == plugin_count
    assert result.next_offset == (1 if plugin_count > 1 else None)
    assert result.items[0].model_dump() == original.plugins[0].model_dump(exclude={"shared_origin"})
    assert result.items[0].skill_names == ["my-skill"]
    assert result.items[0].server_names == ["my-server"]
    second = await read_plugins(async_session, owner, PluginReadInput(offset=1))
    assert {item.id for item in (*result.items, *second.items)} == {row.id for row in rows}
    assert other.id not in {item.id for item in second.items}
    raw = result.model_dump_json() + second.model_dump_json()
    assert all(
        secret not in raw
        for secret in [
            "secret",
            "manifest",
            "foreign-skill",
            "foreign-server",
            "https://",
            "Private sender",
            str(receipt.id),
            "shared_origin",
        ]
    )
