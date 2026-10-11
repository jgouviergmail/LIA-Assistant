"""Changes after package staging must be refused before the final root commit."""

from unittest.mock import AsyncMock

import pytest

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.plugin_url_import import (
    execute_plugin_url_import,
    prepare_plugin_url_import,
)
from src.domains.agents.application.plugin_url_import_schemas import PluginUrlImportInput
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.domains.skills.test_per_account_skill_names import _skill
from tests.integration.test_application_plugin_read import _plugin
from tests.integration.test_application_plugin_url_import import _package

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("target", ["root", "dropped_skill"])
async def test_native_plugin_import_rechecks_recoverable_files_after_staging(
    async_session, test_user, monkeypatch, tmp_path, target
):
    for key in (
        "application_tools_enabled",
        "plugins_enabled",
        "skills_url_import_enabled",
        "skills_enabled",
    ):
        monkeypatch.setattr(settings, key, True)
    monkeypatch.setattr(settings, "plugins_users_path", str(tmp_path / "plugins"))
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path / "skills"))
    monkeypatch.setattr("src.domains.skills.cache.SkillsCache.invalidate_and_reload", AsyncMock())
    owner = test_user.id
    plugin = await _plugin(async_session, owner, "native-plugin")
    plugin_id = plugin.id
    root = tmp_path / "plugins" / str(owner) / plugin.name
    root.mkdir(parents=True)
    previous = root / "old.bin"
    previous.write_bytes(b"previous root")
    member = await _skill(async_session, "dropped-skill", owner)
    member.plugin_id = plugin_id
    skill_root = tmp_path / "skills" / str(owner) / member.name
    skill_root.mkdir(parents=True)
    resource = skill_root / "resource.bin"
    resource.write_bytes(b"previous skill")
    await async_session.commit()
    monkeypatch.setattr(
        "src.domains.agents.application.plugin_url_import.fetch_skill_from_url",
        AsyncMock(return_value=(_package(), "native.zip")),
    )
    monkeypatch.setattr(
        "src.domains.agents.application.plugin_url_import.rate_limit_url_import", AsyncMock()
    )
    draft = await prepare_plugin_url_import(
        async_session,
        owner,
        PluginUrlImportInput(
            url="https://source.example/package.zip",
            replace_plugin_id=plugin_id,
        ),
    )
    if target == "root":
        from src.domains.plugins import root_commit

        original = root_commit.stage_root

        def change_staged(source, slot):
            original(source, slot)
            (slot.previous / "old.bin").write_bytes(b"changed during staging")

        monkeypatch.setattr(root_commit, "stage_root", change_staged)
    else:
        from src.domains.plugins import dropped_files

        original = dropped_files.stage_moves

        def change_staged(moves):
            original(moves)
            (moves[0].destination / "resource.bin").write_bytes(b"changed during staging")

        monkeypatch.setattr(dropped_files, "stage_moves", change_staged)
    receipt = PreferenceWriteReceipt()
    with pytest.raises(CommandRejected, match="STALE_STATE"):
        await execute_plugin_url_import(async_session, owner, draft, receipt)
    assert not receipt.committed
    assert previous.read_bytes() == (
        b"changed during staging" if target == "root" else b"previous root"
    )
    assert resource.read_bytes() == (
        b"changed during staging" if target == "dropped_skill" else b"previous skill"
    )
