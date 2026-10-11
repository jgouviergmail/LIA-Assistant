"""The existing UI endpoint uses the same staged SQL/known-ack byte boundary."""

from unittest.mock import AsyncMock

import pytest

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.skills.cache import SkillsCache
from src.domains.skills.router import delete_skill
from tests.integration.domains.skills.test_per_account_skill_names import _skill

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("lost_ack", [False, True])
async def test_original_skill_delete_does_not_unlink_before_known_commit(
    async_session, test_user, monkeypatch, tmp_path, lost_ack
):
    owner = test_user.id
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path))
    row = await _skill(async_session, "ui-delete-card", owner)
    root = tmp_path / str(owner) / row.name
    root.mkdir(parents=True)
    file = root / "SKILL.md"
    file.write_text("Approved old skill", encoding="utf-8")
    cached = {"name": row.name, "scope": "user", "owner_id": str(owner), "source_path": str(file)}
    monkeypatch.setattr(SkillsCache, "get_by_name_for_user", lambda *args: cached)
    monkeypatch.setattr(SkillsCache, "get_exact", lambda *args: cached)
    monkeypatch.setattr(SkillsCache, "invalidate_and_reload", AsyncMock())
    await async_session.commit()
    if lost_ack:

        async def unknown_commit():
            raise OSError("lost acknowledgement")

        monkeypatch.setattr(async_session, "commit", unknown_commit)
        with pytest.raises((OSError, BaseAPIException)):
            await delete_skill(row.name, test_user, async_session)
        assert file.exists()
    else:
        await delete_skill(row.name, test_user, async_session)
        assert not file.exists()
