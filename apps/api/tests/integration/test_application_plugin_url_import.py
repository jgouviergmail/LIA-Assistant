"""Native URL package imports are source-sealed, account-owned and honest about commit ACKs."""

import io
import json
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.core.constants import AGENT_PLUGINS_PLUGIN_SCHEMA_ID
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.plugin_url_import import (
    execute_plugin_url_import,
    prepare_plugin_url_import,
)
from src.domains.agents.application.plugin_url_import_schemas import PluginUrlImportInput
from src.domains.plugins.models import UserPlugin
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_application_plugin_read import _plugin

pytestmark = pytest.mark.integration


def _package(version="2.0", skills=False, description=None, name="native-plugin"):
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "plugin.json",
            json.dumps(
                {
                    "$schema": AGENT_PLUGINS_PLUGIN_SCHEMA_ID,
                    "name": name,
                    "version": version,
                    **({"description": description} if description is not None else {}),
                }
            ),
        )
        if skills:
            archive.writestr(
                "skills/my-skill/SKILL.md",
                "---\nname: my-skill\ndescription: Public description.\n---\nPrivate instructions",
            )
    return buffer.getvalue()


@pytest.mark.parametrize(
    "scenario",
    [
        "fresh",
        "replace",
        "remote_changed",
        "local_changed",
        "operator_off",
        "lost_ack",
        "partial_unknown",
        "observer_failed",
    ],
)
async def test_native_plugin_url_import_seals_source_and_exact_owned_installation(
    async_session, test_user, monkeypatch, tmp_path, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "plugins_enabled", True)
    monkeypatch.setattr(settings, "skills_url_import_enabled", True)
    monkeypatch.setattr(settings, "skills_enabled", True)
    monkeypatch.setattr("src.domains.skills.cache.SkillsCache.invalidate_and_reload", AsyncMock())
    monkeypatch.setattr(settings, "plugins_users_path", str(tmp_path / "plugins"))
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path / "skills"))
    owner = test_user.id
    previous_id = None
    root = tmp_path / "plugins" / str(owner) / "native-plugin"
    if scenario in {"replace", "local_changed"}:
        previous = await _plugin(async_session, owner, "native-plugin")
        previous_id = previous.id
        root.mkdir(parents=True)
        (root / "old.bin").write_bytes(b"old-private-version")
    await async_session.commit()
    fetch = AsyncMock(return_value=(_package(skills=scenario == "partial_unknown"), "native.zip"))
    limit = AsyncMock()
    monkeypatch.setattr(
        "src.domains.agents.application.plugin_url_import.fetch_skill_from_url", fetch
    )
    monkeypatch.setattr(
        "src.domains.agents.application.plugin_url_import.rate_limit_url_import", limit
    )
    draft = await prepare_plugin_url_import(
        async_session,
        owner,
        PluginUrlImportInput(
            url="https://source.example/native.zip", replace_plugin_id=previous_id
        ),
    )
    assert all(
        secret not in draft.model_dump_json() for secret in ["old-private-version", str(tmp_path)]
    )
    assert "package_digest" not in json.dumps(draft.after)
    receipt = PreferenceWriteReceipt()
    if scenario == "remote_changed":
        fetch.return_value = (_package("changed"), "native.zip")
    elif scenario == "local_changed":
        (root / "old.bin").write_bytes(b"changed-locally")
    elif scenario == "operator_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif scenario == "observer_failed":
        from src.domains.plugins.import_hooks import PluginImportHooks

        def observer_failed(_hooks, _row):
            raise RuntimeError("commit observer failed before recording its receipt")

        monkeypatch.setattr(PluginImportHooks, "root_committed", observer_failed)
    elif scenario in {"lost_ack", "partial_unknown"}:
        original_commit = async_session.commit
        calls = 0

        async def commit():
            nonlocal calls
            calls += 1
            await original_commit()
            # The first commit releases the URL fetch read transaction.
            if calls == (3 if scenario == "partial_unknown" else 2):
                raise ConnectionError("database committed; ACK lost")

        monkeypatch.setattr(async_session, "commit", commit)
    if scenario in {
        "remote_changed",
        "local_changed",
        "operator_off",
        "lost_ack",
        "partial_unknown",
        "observer_failed",
    }:
        with pytest.raises((CommandRejected, BaseAPIException)) as caught:
            await execute_plugin_url_import(async_session, owner, draft, receipt)
        if scenario == "observer_failed":
            assert caught.value.code == "POST_COMMIT_FAILURE"
            assert receipt.committed and receipt.values["plugin_url_import"]["complete"] is True
            assert root.exists() and receipt.values["file_cleanup_pending"] is True
        elif scenario == "partial_unknown":
            assert caught.value.code == "COMPLETION_UNKNOWN"
            assert receipt.committed and receipt.values["completion_unknown"] is True
            assert receipt.values["plugin_url_import"]["installed_skill_names"] == ["my-skill"]
            assert receipt.values["plugin_url_import"]["complete"] is False
            assert root.exists()
        elif scenario == "lost_ack":
            assert caught.value.code == "COMPLETION_UNKNOWN"
            assert not receipt.committed and root.exists()
        else:
            assert not receipt.committed
        if scenario == "local_changed":
            assert (root / "old.bin").read_bytes() == b"changed-locally"
    else:
        await execute_plugin_url_import(async_session, owner, draft, receipt)
        assert receipt.committed
        assert receipt.values["plugin_url_import"]["version"] == "2.0"
        row = await async_session.scalar(select(UserPlugin).where(UserPlugin.user_id == owner))
        assert row is not None and row.name == "native-plugin"
        if previous_id is not None:
            assert row.id == previous_id
        assert json.loads((root / "plugin.json").read_bytes())["version"] == "2.0"
