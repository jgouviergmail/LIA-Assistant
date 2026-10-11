"""A native plugin removal seals the complete group and acts only on the approved version."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.plugin_delete import (
    execute_plugin_deletion,
    prepare_plugin_deletion,
)
from src.domains.agents.application.plugin_delete_schemas import PluginDeleteInput
from src.domains.plugins.models import UserPlugin
from src.domains.skills.cache import SkillsCache
from src.domains.skills.models import Skill
from src.domains.user_mcp.models import UserMCPServer
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.domains.skills.test_per_account_skill_names import _skill
from tests.integration.test_application_plugin_read import _plugin

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "files_changed",
        "changed_during_stage",
        "server_changed",
        "operator_off",
        "plugins_off",
        "revoked",
        "lost_ack",
        "cache",
    ],
)
async def test_plugin_removal_freezes_group_files_and_preserves_commit_truth(
    async_session, test_user, monkeypatch, tmp_path, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "plugins_enabled", True)
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path / "skills"))
    monkeypatch.setattr(settings, "plugins_users_path", str(tmp_path / "plugins"))
    owner = test_user.id
    plugin = await _plugin(async_session, owner, "approved-plugin")
    skill = await _skill(async_session, "approved-skill", owner)
    skill.plugin_id = plugin.id
    server = UserMCPServer(
        user_id=owner,
        name="approved-api",
        url="https://example.com",
        plugin_id=plugin.id,
        credentials_encrypted="private encrypted credential",
    )
    async_session.add(server)
    await async_session.flush()
    plugin_id, skill_id = plugin.id, skill.id
    root = tmp_path / "skills" / str(owner) / skill.name
    root.mkdir(parents=True)
    file = root / "SKILL.md"
    file.write_bytes(b"Private skill instructions")
    monkeypatch.setattr(
        SkillsCache,
        "invalidate_and_reload",
        AsyncMock(side_effect=OSError("cache") if scenario == "cache" else None),
    )
    monkeypatch.setattr(
        "src.domains.user_mcp.service.UserMCPServerService._disconnect_from_pool", AsyncMock()
    )
    await async_session.commit()
    draft = await prepare_plugin_deletion(
        async_session, owner, PluginDeleteInput(plugin_id=plugin_id)
    )
    assert all(
        private not in draft.model_dump_json()
        for private in ["Private skill instructions", "private encrypted credential", str(tmp_path)]
    )
    assert draft.before["plugin_to_delete"]["plugin"]["skill_names"] == [skill.name]
    if scenario == "files_changed":
        file.write_bytes(b"Changed before confirmation")
    elif scenario == "changed_during_stage":
        from src.domains.plugins import removal

        original_stage = removal.stage_moves

        def change_staged(moves):
            original_stage(moves)
            for move in moves:
                member = move.destination / "SKILL.md"
                if member.exists():
                    member.write_bytes(b"Changed during staging")

        monkeypatch.setattr(removal, "stage_moves", change_staged)
    elif scenario == "server_changed":
        server.url = "https://changed.example.com"
        await async_session.commit()
    elif scenario == "operator_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif scenario == "plugins_off":
        monkeypatch.setattr(settings, "plugins_enabled", False)
    elif scenario == "revoked":
        test_user.is_active = False
        await async_session.commit()
    elif scenario == "lost_ack":
        original_commit = async_session.commit

        async def lose_ack():
            await original_commit()
            raise ConnectionError("ACK lost")

        monkeypatch.setattr(async_session, "commit", lose_ack)
    receipt = PreferenceWriteReceipt()
    if scenario in {
        "files_changed",
        "changed_during_stage",
        "server_changed",
        "operator_off",
        "plugins_off",
        "revoked",
        "lost_ack",
    }:
        with pytest.raises((CommandRejected, BaseAPIException)):
            await execute_plugin_deletion(async_session, owner, draft, receipt)
        assert not receipt.committed
        if scenario != "lost_ack":
            assert file.exists()
        else:
            assert list(tmp_path.rglob("SKILL.md"))
    else:
        await execute_plugin_deletion(async_session, owner, draft, receipt)
        assert receipt.committed and receipt.values["plugin_to_delete"] is None
        assert receipt.values["cache_refresh_pending"] == (scenario == "cache")
        assert (
            await async_session.scalar(select(UserPlugin.id).where(UserPlugin.id == plugin_id))
            is None
        )
        assert await async_session.scalar(select(Skill.id).where(Skill.id == skill_id)) is None
        assert not file.exists()
