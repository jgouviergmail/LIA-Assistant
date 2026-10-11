"""Native skill metadata reflects the real UI visibility/shadowing and excludes instructions/paths."""

from unittest.mock import patch

import pytest

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.skill_read import read_skills
from src.domains.agents.application.skill_read_schemas import SkillReadInput
from src.domains.skills.cache import SkillsCache
from tests.integration.domains.skills.test_per_account_skill_names import _skill, _user

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["visible", "shadowed", "disabled", "revoked", "skills_off"])
async def test_skill_list_reuses_owner_visibility_and_hides_private_cache_material(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "skills_enabled", True)
    owner = test_user.id
    own = await _skill(async_session, "owned-card", owner)
    system = await _skill(async_session, "system-card", None)
    foreign = await _skill(async_session, "foreign-card", await _user(async_session))
    hidden = await _skill(async_session, "hidden-card", None)
    hidden.admin_enabled = False
    if scenario == "shadowed":
        await _skill(async_session, "owned-card", None)
    await async_session.commit()
    if scenario == "disabled":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif scenario == "skills_off":
        monkeypatch.setattr(settings, "skills_enabled", False)
    elif scenario == "revoked":
        test_user.is_active = False
        await async_session.commit()
    metadata = {
        "category": "writing",
        "priority": 50,
        "instructions": "private complete instructions",
        "source_path": "private/server/skill",
        "owner_id": "foreign",
        "scripts": ["hidden-script.py"],
    }
    with patch.object(SkillsCache, "get_exact", return_value=metadata) as cache:
        if scenario in {"disabled", "revoked", "skills_off"}:
            with pytest.raises(BaseAPIException):
                await read_skills(async_session, owner, SkillReadInput())
        else:
            result = await read_skills(async_session, owner, SkillReadInput(limit=1))
            assert result.total == 2 and len(result.items) == 1 and result.next_offset == 1
            second = await read_skills(async_session, owner, SkillReadInput(limit=1, offset=1))
            ids = {item.skill_id for item in (*result.items, *second.items)}
            assert ids == {own.id, system.id} and foreign.id not in ids
            assert {call.args for call in cache.call_args_list} == {
                ("owned-card", str(owner)),
                ("system-card", None),
            }
            raw = result.model_dump_json() + second.model_dump_json()
            assert (
                "private complete instructions" not in raw
                and "private/server" not in raw
                and "hidden-script.py" not in raw
            )
