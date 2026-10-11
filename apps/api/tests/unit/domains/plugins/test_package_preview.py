"""Original plugin parsing previews full file/component scope without leaking package secrets."""

import asyncio
import io
import json
import threading
from unittest.mock import MagicMock
from zipfile import ZipFile

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import AGENT_PLUGINS_MCP_SCHEMA_ID, AGENT_PLUGINS_PLUGIN_SCHEMA_ID
from src.core.exceptions import BaseAPIException
from src.domains.plugins.import_service import PluginImportService
from src.domains.plugins.package_preview import (
    PluginPackagePreview,
    PluginPackageServer,
    preview_plugin_package,
)
from src.domains.plugins.schemas import McpServerValidation, PluginManifest

pytestmark = pytest.mark.unit


def _package() -> bytes:
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr(
            "plugin.json",
            json.dumps(
                {
                    "$schema": AGENT_PLUGINS_PLUGIN_SCHEMA_ID,
                    "name": "my-plugin",
                    "description": "Public description",
                    "extensions": {"private": {"token": "private manifest token"}},
                }
            ),
        )
        archive.writestr(
            "skills/renamed-folder/SKILL.md",
            "---\nname: actual-skill\ndescription: public\n---\nPrivate skill instructions",
        )
        archive.writestr("skills/renamed-folder/scripts/run.py", "private executable content")
        archive.writestr(
            "mcp.json",
            json.dumps(
                {
                    "$schema": AGENT_PLUGINS_MCP_SCHEMA_ID,
                    "mcpServers": {
                        "lookup": {
                            "type": "streamable-http",
                            "url": "https://example.com/mcp?token=private-query",
                            "headers": {"Authorization": "Bearer private-header"},
                        },
                        "local": {"type": "stdio", "command": "private-command"},
                    },
                }
            ),
        )
    return output.getvalue()


@pytest.mark.asyncio
async def test_original_preview_is_complete_and_read_only() -> None:
    db = MagicMock(spec=AsyncSession)
    result = await preview_plugin_package(PluginImportService(db), _package())
    assert result.name == "my-plugin"
    assert result.skill_names == ("actual-skill",)
    assert result.has_scripts
    assert len(result.files) == 4
    assert {server.key for server in result.servers} == {"lookup", "local"}
    assert result.servers[0].has_headers
    assert result.servers[0].host == "example.com"
    raw = result.model_dump_json()
    assert all(
        private not in raw
        for private in [
            "Private skill instructions",
            "private executable",
            "private manifest",
            "private-header",
            "private-query",
            "private-command",
            "Authorization",
            "staging",
        ]
    )
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.add.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["invalid", "oversized"])
async def test_invalid_preview_cannot_reach_install(monkeypatch, scenario) -> None:
    monkeypatch.setattr(settings, "plugins_max_file_size_kb", 1)
    content = b"invalid" if scenario == "invalid" else b"x" * 1025
    db = MagicMock(spec=AsyncSession)
    with pytest.raises(BaseAPIException):
        await preview_plugin_package(PluginImportService(db), content)
    db.commit.assert_not_awaited()


def test_new_package_or_transport_fields_require_explicit_preview_review() -> None:
    assert set(PluginManifest.model_fields) == {
        "schema_id",
        "name",
        "version",
        "description",
        "author",
        "homepage",
        "repository",
        "license",
        "keywords",
        "extensions",
    }
    assert set(McpServerValidation.model_fields) == {
        "key",
        "status",
        "transport",
        "url",
        "headers",
        "issues",
    }
    assert set(PluginPackagePreview.model_fields) == {
        "name",
        "version",
        "description",
        "spec_version",
        "skill_names",
        "has_scripts",
        "servers",
        "files",
        "warnings",
    }
    assert set(PluginPackageServer.model_fields) == {
        "key",
        "status",
        "transport",
        "host",
        "has_headers",
        "issues",
    }


@pytest.mark.asyncio
async def test_repeated_cancellation_finishes_the_owned_worker_before_staging_cleanup(
    monkeypatch,
) -> None:
    from src.domains.plugins import package_preview

    started, release = threading.Event(), threading.Event()
    observed = []
    original = package_preview._preview

    def delayed(service, content, root):
        result = original(service, content, root)
        observed.append(root)
        started.set()
        assert release.wait(timeout=5)
        assert root.exists(), "staging was removed while the worker was still using it"
        return result

    monkeypatch.setattr(package_preview, "_preview", delayed)
    task = asyncio.create_task(
        preview_plugin_package(PluginImportService(MagicMock(spec=AsyncSession)), _package())
    )
    try:
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        task.cancel()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert observed and not observed[0].exists()
