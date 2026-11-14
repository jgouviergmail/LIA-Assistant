"""The assistant reads a skill's life as the settings show it (lot 14).

Its use since counting began, the dormancy verdict and the way back to a
previous version reach the assistant's skill read, while the identity a
confirmation seals (``SkillReadItem``) stays the reviewed metadata alone.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.skill_read import observe_visible_skill, read_skills
from src.domains.agents.application.skill_read_schemas import SkillReadInput, SkillReadItem
from src.domains.skills.import_service import SkillImportService
from tests.helpers.committed_account_session import async_session as async_session
from tests.integration.domains.skill_library.test_library_install import _user
from tests.integration.domains.skill_library.test_library_install import skill_dirs as skill_dirs
from tests.unit.domains.skill_library.fakes import manifest

pytestmark = pytest.mark.integration


async def test_the_assistant_reads_the_use_and_the_way_back_the_settings_show(
    async_session: AsyncSession, skill_dirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "skills_enabled", True)
    actor = await _user(async_session)
    service = SkillImportService(async_session)
    for words in ("First words", "Second words"):
        await service.import_upload(
            manifest("notes", words), "SKILL.md", owner_id=actor, is_system=False
        )

    result = await read_skills(async_session, actor, SkillReadInput())

    assert result.dormant_after_days == settings.skills_dormant_after_days
    (entry,) = [item for item in result.items if item.name == "notes"]
    assert (entry.use_count, entry.last_used_at, entry.dormant) == (0, None, False)
    assert isinstance(entry.counted_since, datetime)
    assert isinstance(entry.previous_version_at, datetime)
    # The identity a confirmation seals carries none of it: a use between the
    # draft and its confirmation must never read as a changed skill.
    sealed = await observe_visible_skill(async_session, actor, entry.skill_id)
    assert type(sealed) is SkillReadItem
    assert sealed == SkillReadItem.model_validate(
        entry.model_dump(include=set(SkillReadItem.model_fields))
    )
