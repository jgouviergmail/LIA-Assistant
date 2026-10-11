"""The original service uses the recoverable root port with real PostgreSQL commits."""

import io
import json
from zipfile import ZipFile

import pytest
from sqlalchemy.exc import IntegrityError

from src.core.config import settings
from src.core.constants import AGENT_PLUGINS_PLUGIN_SCHEMA_ID
from src.domains.plugins.import_service import PluginImportService
from src.domains.plugins.root_commit import PluginImportCompletionUnknown
from tests.integration.test_application_plugin_read import _plugin

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["success", "rejected", "lost_ack"])
async def test_original_plugin_import_preserves_root_and_database_truth(
    async_session, test_user, monkeypatch, tmp_path, scenario
):
    monkeypatch.setattr(settings, "plugins_users_path", str(tmp_path))
    row = await _plugin(async_session, test_user.id, "database-plugin")
    root = tmp_path / str(test_user.id) / row.name
    root.mkdir(parents=True)
    previous = root / "plugin.json"
    previous.write_bytes(b"previous version")
    buffer = io.BytesIO()
    package = {"$schema": AGENT_PLUGINS_PLUGIN_SCHEMA_ID, "name": row.name, "version": "2.0.0"}
    with ZipFile(buffer, "w") as archive:
        archive.writestr("plugin.json", json.dumps(package))
    original_commit = async_session.commit
    calls = 0

    async def commit():
        nonlocal calls
        calls += 1
        if scenario == "rejected":
            raise IntegrityError("commit", {}, ValueError("rejected"))
        await original_commit()
        if scenario == "lost_ack":
            raise ConnectionError("commit acknowledged by PostgreSQL, reply lost")

    monkeypatch.setattr(async_session, "commit", commit)
    if scenario == "rejected":
        with pytest.raises(IntegrityError):
            await PluginImportService(async_session).import_upload(
                buffer.getvalue(), owner_id=test_user.id
            )
        assert previous.read_bytes() == b"previous version"
    elif scenario == "lost_ack":
        with pytest.raises(PluginImportCompletionUnknown):
            await PluginImportService(async_session).import_upload(
                buffer.getvalue(), owner_id=test_user.id
            )
        assert json.loads(previous.read_bytes())["version"] == "2.0.0"
        assert any(
            path.read_bytes() == b"previous version" for path in tmp_path.rglob("plugin.json")
        )
    else:
        result = await PluginImportService(async_session).import_upload(
            buffer.getvalue(), owner_id=test_user.id
        )
        assert result.version == "2.0.0" and not result.file_cleanup_pending
        assert json.loads(previous.read_bytes())["version"] == "2.0.0"
    assert calls == 1
