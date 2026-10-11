"""The original named download cannot bypass the gallery's disabled/shadowing visibility."""

import pytest

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.skills.cache import SkillsCache
from src.domains.skills.router import download_skill
from tests.integration.domains.skills.test_per_account_skill_names import _skill

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("hidden", [False, True, "during_export"])
async def test_original_skill_download_refuses_disabled_system_skill(
    async_session, test_user, monkeypatch, tmp_path, hidden
):
    monkeypatch.setattr(settings, "skills_system_path", str(tmp_path))
    row = await _skill(async_session, "system-card", None)
    row.admin_enabled = hidden is not True
    await async_session.commit()
    root = tmp_path / row.name
    root.mkdir()
    (root / "SKILL.md").write_text("System skill instructions", encoding="utf-8")
    cached = {
        "name": row.name,
        "scope": "admin",
        "owner_id": None,
        "source_path": str(root / "SKILL.md"),
    }
    monkeypatch.setattr(SkillsCache, "get_by_name_for_user", lambda *args: cached)
    monkeypatch.setattr(SkillsCache, "get_exact", lambda *args: cached)
    kwargs = {"skill_name": row.name, "user": test_user}
    kwargs["db"] = async_session
    if hidden == "during_export":
        from src.domains.skills import router

        original_thread = router.asyncio.to_thread

        async def revoke_after_export(function, *args):
            result = await original_thread(function, *args)
            row.admin_enabled = False
            await async_session.commit()
            return result

        monkeypatch.setattr(router.asyncio, "to_thread", revoke_after_export)
    if hidden:
        with pytest.raises(BaseAPIException):
            await download_skill(**kwargs)
    else:
        response = await download_skill(**kwargs)
        assert response.media_type == "application/zip"
