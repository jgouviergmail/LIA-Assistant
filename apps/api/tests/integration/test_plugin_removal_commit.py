"""Plugin group deletion preserves bytes before commit and reports its actual completion."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import settings
from src.domains.plugins.removal import PluginRemovalCompletionUnknown, remove_plugin
from src.domains.skills.cache import SkillsCache
from src.domains.user_mcp.models import UserMCPServer
from tests.integration.domains.skills.test_per_account_skill_names import _skill
from tests.integration.test_application_plugin_read import _plugin

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario", ["success", "before_commit", "lost_ack", "cleanup", "pool", "cache"]
)
async def test_original_group_removal_preserves_precommit_bytes_and_known_truth(
    async_session, test_user, monkeypatch, tmp_path, scenario
):
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path / "skills"))
    monkeypatch.setattr(settings, "plugins_users_path", str(tmp_path / "plugins"))
    owner = test_user.id
    plugin = await _plugin(async_session, owner, "complete-plugin")
    skill = await _skill(async_session, "complete-skill", owner)
    skill.plugin_id = plugin.id
    server = UserMCPServer(
        user_id=owner, name="complete-api", url="https://example.com", plugin_id=plugin.id
    )
    async_session.add(server)
    await async_session.flush()
    for root, name, member in [
        (settings.skills_users_path, skill.name, "SKILL.md"),
        (settings.plugins_users_path, plugin.name, "plugin.json"),
    ]:
        folder = Path(root) / str(owner) / name
        folder.mkdir(parents=True)
        content = (
            b"---\nname: complete-skill\ndescription: original bytes\n---\nRun the original action.\n"
            if member == "SKILL.md"
            else b"original bytes"
        )
        (folder / member).write_bytes(content)
    skill_file = Path(settings.skills_users_path) / str(owner) / skill.name / "SKILL.md"
    original_bytes = skill_file.read_bytes()
    original_commit = async_session.commit

    async def commit() -> None:
        assert not skill_file.exists()
        await original_commit()
        if scenario == "lost_ack":
            raise ConnectionError("ack lost after commit")

    async def fence() -> None:
        if scenario == "before_commit":
            raise ValueError("revoked before commit")

    monkeypatch.setattr(async_session, "commit", commit)
    cleanup = (
        patch("src.domains.plugins.removal.cleanup_quarantine", side_effect=OSError("busy"))
        if scenario == "cleanup"
        else patch("src.domains.plugins.removal.logger")
    )
    with (
        patch(
            "src.domains.user_mcp.service.UserMCPServerService._disconnect_from_pool",
            AsyncMock(side_effect=ConnectionError("pool") if scenario == "pool" else None),
        ) as pool,
        patch.object(
            SkillsCache,
            "invalidate_and_reload",
            AsyncMock(side_effect=ConnectionError("cache") if scenario == "cache" else None),
        ),
        cleanup,
    ):
        if scenario == "before_commit":
            with pytest.raises(ValueError):
                await remove_plugin(async_session, owner, plugin.id, before_commit=fence)
            assert skill_file.read_bytes() == original_bytes
            pool.assert_not_awaited()
        elif scenario == "lost_ack":
            with pytest.raises(PluginRemovalCompletionUnknown):
                await remove_plugin(async_session, owner, plugin.id, before_commit=fence)
            assert not skill_file.exists()
            assert list(tmp_path.rglob("SKILL.md")), "unknown commit destroyed recoverable bytes"
            pool.assert_not_awaited()
        else:
            result = await remove_plugin(async_session, owner, plugin.id, before_commit=fence)
            assert result.committed
            assert result.file_cleanup_pending == (scenario == "cleanup")
            assert result.pool_cleanup_pending == (scenario == "pool")
            assert result.cache_refresh_pending == (scenario == "cache")
            assert not skill_file.exists()
            assert pool.await_args.kwargs == {"strict": True}
        if scenario in {"cleanup", "lost_ack"}:
            from src.domains.skills.loader import scan_skills_directory

            assert (
                scan_skills_directory(
                    Path(settings.skills_users_path) / str(owner), scope="user", owner_id=str(owner)
                )
                == []
            ), "quarantined skills were rediscovered"
