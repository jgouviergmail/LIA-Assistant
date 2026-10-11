"""Native fences use original import commits and never disguise authorization as a skipped skill."""

import io
import json
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest

from src.core.config import settings
from src.core.constants import AGENT_PLUGINS_PLUGIN_SCHEMA_ID
from src.core.exceptions import AuthorizationError
from src.domains.plugins.import_hooks import PluginImportHooks
from src.domains.plugins.import_service import PluginImportService
from src.domains.skills.repository import SkillRepository

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("boundary", ["initial", "second_skill", "root_commit"])
async def test_authority_refusal_stops_original_pipeline_and_known_commits_are_reported(
    async_session, test_user, monkeypatch, tmp_path, boundary
):
    monkeypatch.setattr(settings, "plugins_users_path", str(tmp_path / "plugins"))
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path / "skills"))
    monkeypatch.setattr("src.domains.skills.cache.SkillsCache.invalidate_and_reload", AsyncMock())
    owner = test_user.id
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "plugin.json",
            json.dumps({"$schema": AGENT_PLUGINS_PLUGIN_SCHEMA_ID, "name": "fenced-plugin"}),
        )
        if boundary == "second_skill":
            for name in ("first-skill", "second-skill"):
                archive.writestr(
                    f"skills/{name}/SKILL.md",
                    f"---\nname: {name}\ndescription: Useful plugin skill.\n---\nBody.\n",
                )
    swaps = 0
    committed = []
    root_committed = []

    async def refuse(_session):
        raise AuthorizationError("capability revoked")

    async def before_swap(_session, _path):
        nonlocal swaps
        swaps += 1
        if swaps == 2:
            await refuse(_session)

    hooks = PluginImportHooks(
        before_write=refuse if boundary == "initial" else None,
        before_skill_swap=before_swap,
        before_commit=refuse if boundary == "root_commit" else None,
        after_skill_commit=lambda row: committed.append(row.name),
        after_root_commit=lambda row: root_committed.append(row.name),
    )
    with pytest.raises(AuthorizationError):
        await PluginImportService(async_session).import_upload(
            buffer.getvalue(), owner_id=owner, hooks=hooks
        )
    assert root_committed == []
    assert not (tmp_path / "plugins" / str(owner) / "fenced-plugin").exists()
    if boundary == "second_skill":
        assert committed == ["first-skill"] and swaps == 2
        assert await SkillRepository(async_session).get_owned(owner, "first-skill") is not None
        assert await SkillRepository(async_session).get_owned(owner, "second-skill") is None
    else:
        assert committed == []
