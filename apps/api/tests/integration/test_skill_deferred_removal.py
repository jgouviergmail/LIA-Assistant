"""Skill row deletion is staged without touching bytes before a known commit."""

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.domains.skills.cache import SkillsCache
from src.domains.skills.models import Skill
from src.domains.skills.removal import cleanup_removal, observe_removal, stage_removal
from tests.integration.domains.skills.test_per_account_skill_names import _skill, _user

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "rollback",
        "committed",
        "changed_file",
        "missing_disk",
        "reinstalled",
        "foreign_state",
        "foreign",
        "plugin",
    ],
)
async def test_staged_owned_skill_delete_preserves_uncommitted_and_changed_files(
    async_session, test_user, monkeypatch, tmp_path, scenario
):
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path))
    owner = test_user.id
    actual_owner = await _user(async_session) if scenario == "foreign" else owner
    row = await _skill(async_session, "delete-card", actual_owner)
    identity = row.id
    root = tmp_path / str(actual_owner) / row.name
    root.mkdir(parents=True)
    file = root / "SKILL.md"
    file.write_text("approved bytes", encoding="utf-8")
    cached = {
        "name": row.name,
        "scope": "user",
        "owner_id": str(actual_owner),
        "source_path": str(file),
    }
    monkeypatch.setattr(
        SkillsCache,
        "get_exact",
        lambda name, owner_id: cached if owner_id == str(actual_owner) else None,
    )
    await async_session.commit()
    if scenario == "foreign_state":
        from src.domains.skills.models import UserSkillState

        async_session.add(
            UserSkillState(user_id=await _user(async_session), skill_id=identity, is_active=True)
        )
        await async_session.commit()
    if scenario == "plugin":
        # A real plugin row owns the FK: native removal must not amputate its component.
        from src.domains.plugins.models import UserPlugin

        plugin = UserPlugin(
            user_id=owner,
            name="plugin-card",
            version="1.0",
            description="owned",
            spec_version="1.0.0",
            manifest={"name": "plugin-card", "specVersion": "1.0.0"},
        )
        async_session.add(plugin)
        await async_session.flush()
        row.plugin_id = plugin.id
        await async_session.commit()
    if scenario in {"foreign", "plugin", "foreign_state"}:
        with pytest.raises(ValueError):
            await observe_removal(async_session, owner, identity)
        assert file.read_text(encoding="utf-8") == "approved bytes"
        return
    observed = await observe_removal(async_session, owner, identity)
    if scenario == "missing_disk":
        file.unlink()
        root.rmdir()
        observed = await observe_removal(async_session, owner, identity)
    await stage_removal(async_session, owner, observed)
    if scenario != "missing_disk":
        assert file.read_text(encoding="utf-8") == "approved bytes"
    assert await async_session.scalar(select(Skill.id).where(Skill.id == identity)) is None
    if scenario == "rollback":
        await async_session.rollback()
        assert file.exists()
    else:
        await async_session.commit()
        if scenario == "changed_file":
            file.write_text("newer bytes", encoding="utf-8")
        elif scenario == "reinstalled":
            await _skill(async_session, "delete-card", owner)
            await async_session.commit()
        cleaned = await cleanup_removal(async_session, observed)
        assert cleaned == (scenario in {"committed", "missing_disk"})
        assert file.exists() == (scenario in {"changed_file", "reinstalled"})
