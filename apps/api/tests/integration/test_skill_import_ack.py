"""A lost commit ACK never restores older files beside a durably updated skill row."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.domains.skills.cache import SkillsCache
from src.domains.skills.import_service import SkillImportService
from src.domains.skills.models import Skill

pytestmark = pytest.mark.integration


def _files(body):
    return {
        "SKILL.md": f"---\nname: ack-card\ndescription: Complete test-only skill for acknowledgement verification\n---\n\n{body}\n"
    }


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("cancelled", [False, True])
async def test_lost_import_commit_ack_preserves_the_newly_committed_package(
    async_session, test_user, monkeypatch, tmp_path, existing, cancelled
):
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path / "users"))
    monkeypatch.setattr(settings, "skills_system_path", str(tmp_path / "system"))
    monkeypatch.setattr(SkillsCache, "_skills", {})
    monkeypatch.setattr(SkillsCache, "invalidate_and_reload", AsyncMock())
    owner = test_user.id
    await async_session.commit()
    importer = SkillImportService(async_session)
    if existing:
        await importer.import_files(_files("Original old instructions"), owner_id=owner)
    original_commit = async_session.commit

    async def lost_commit():
        await original_commit()
        if cancelled:
            import asyncio

            raise asyncio.CancelledError()
        raise OSError("lost acknowledgement after commit")

    monkeypatch.setattr(async_session, "commit", lost_commit)
    from src.domains.skills.import_commit import SkillImportCompletionUnknown

    with pytest.raises(SkillImportCompletionUnknown):
        await importer.import_files(_files("New approved instructions"), owner_id=owner)
    row = await async_session.scalar(
        select(Skill).where(Skill.owner_id == owner, Skill.name == "ack-card")
    )
    assert row is not None
    file = tmp_path / "users" / str(owner) / "ack-card" / "SKILL.md"
    assert file.exists() and "New approved instructions" in file.read_text(encoding="utf-8")
