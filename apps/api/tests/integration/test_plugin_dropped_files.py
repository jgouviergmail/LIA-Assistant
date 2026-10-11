"""Dropped skill bytes remain recoverable until the package update commit is known."""

import io
import json
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest
from sqlalchemy.exc import IntegrityError

from src.core.config import settings
from src.core.constants import AGENT_PLUGINS_PLUGIN_SCHEMA_ID
from src.domains.plugins.import_service import PluginImportService
from src.domains.plugins.root_commit import PluginImportCompletionUnknown
from tests.integration.domains.skills.test_per_account_skill_names import _skill
from tests.integration.test_application_plugin_read import _plugin

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "outcome",
    ["success", "rejected", "lost_ack", "cleanup_pending", "stage_refused", "observer_failed"],
)
async def test_dropped_skill_files_follow_acknowledged_update_commit(
    async_session, test_user, monkeypatch, tmp_path, outcome
):
    monkeypatch.setattr(settings, "plugins_users_path", str(tmp_path / "plugins"))
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path / "skills"))
    monkeypatch.setattr("src.domains.skills.cache.SkillsCache.invalidate_and_reload", AsyncMock())
    owner = test_user.id
    plugin = await _plugin(async_session, owner, "drop-update")
    skill = await _skill(async_session, "dropped-resource", owner)
    skill.plugin_id = plugin.id
    await async_session.flush()
    skill_id = skill.id
    await async_session.commit()
    directory = tmp_path / "skills" / str(owner) / skill.name
    directory.mkdir(parents=True)
    resource = directory / "resource.bin"
    resource.write_bytes(b"recoverable-private-resource")
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "plugin.json",
            json.dumps({"$schema": AGENT_PLUGINS_PLUGIN_SCHEMA_ID, "name": plugin.name}),
        )
    commit = async_session.commit

    async def controlled_commit():
        if outcome == "rejected":
            raise IntegrityError("commit", {}, ValueError("refused"))
        await commit()
        if outcome == "lost_ack":
            raise ConnectionError("database committed; acknowledgement lost")

    monkeypatch.setattr(async_session, "commit", controlled_commit)
    service = PluginImportService(async_session)
    if outcome == "observer_failed":
        from src.domains.plugins.import_hooks import PluginImportHooks

        def observer_refused(_row):
            raise RuntimeError("post-commit observer failed")

        with pytest.raises(RuntimeError):
            await service.import_upload(
                buffer.getvalue(),
                owner_id=owner,
                hooks=PluginImportHooks(after_root_commit=observer_refused),
            )
        assert not directory.exists(), "a known row deletion must never restore live skill bytes"
        assert await async_session.get(type(skill), skill_id) is None
        retained = list((tmp_path / "skills").rglob("resource.bin"))
        assert len(retained) == 1 and ".lia-removal" in retained[0].parts
    elif outcome == "cleanup_pending":

        def cleanup_refused(_moves):
            raise PermissionError("private quarantine cleanup refused")

        monkeypatch.setattr("src.domains.plugins.dropped_files.cleanup_quarantine", cleanup_refused)
        report = await service.import_upload(buffer.getvalue(), owner_id=owner)
        assert report.file_cleanup_pending
        assert not directory.exists()
        retained = list((tmp_path / "skills").rglob("resource.bin"))
        assert len(retained) == 1 and ".lia-removal" in retained[0].parts
        assert await async_session.get(type(skill), skill_id) is None
    elif outcome == "stage_refused":
        from src.domains.plugins.dropped_files import stage_moves

        def stage_then_refuse(moves):
            stage_moves(moves)
            raise PermissionError("stage failed after moving a member")

        monkeypatch.setattr("src.domains.plugins.dropped_files.stage_moves", stage_then_refuse)
        with pytest.raises(PermissionError):
            await service.import_upload(buffer.getvalue(), owner_id=owner)
        assert resource.read_bytes() == b"recoverable-private-resource"
        assert await async_session.get(type(skill), skill_id) is not None
    elif outcome == "success":
        report = await service.import_upload(buffer.getvalue(), owner_id=owner)
        assert not report.file_cleanup_pending
        assert not directory.exists()
        assert not list((tmp_path / "skills").rglob("resource.bin"))
        assert await async_session.get(type(skill), skill_id) is None
    elif outcome == "rejected":
        with pytest.raises(IntegrityError):
            await service.import_upload(buffer.getvalue(), owner_id=owner)
        assert resource.read_bytes() == b"recoverable-private-resource"
        assert await async_session.get(type(skill), skill_id) is not None
    else:
        with pytest.raises(PluginImportCompletionUnknown):
            await service.import_upload(buffer.getvalue(), owner_id=owner)
        assert not directory.exists()
        retained = list((tmp_path / "skills").rglob("resource.bin"))
        assert len(retained) == 1 and retained[0].read_bytes() == b"recoverable-private-resource"
        assert ".lia-removal" in retained[0].parts
