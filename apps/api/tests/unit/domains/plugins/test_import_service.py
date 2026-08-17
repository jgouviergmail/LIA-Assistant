"""Unit tests for the plugin import/uninstall orchestrator (ADR-225).

The orchestrator composes already-tested layers (staging, manifest and mcp
validation, the skills ``import_directory`` pipeline, the user MCP service),
so these tests pin the ORCHESTRATION contract:

- §11.3 resilience: per-component failures never abort the install, and every
  outcome lands in the report (LIA's anti-false-success doctrine);
- quotas are pre-checked globally BEFORE any write (ADR-225 consequence);
- a fatal manifest rejects the plugin with nothing created (§5.2);
- update flow: same-name re-import upserts components and removes the ones
  the new version dropped;
- uninstall removes the plugin's components (rows + disk) and its root.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import status

from src.core.constants import (
    AGENT_PLUGINS_MCP_SCHEMA_ID,
    AGENT_PLUGINS_PLUGIN_SCHEMA_ID,
)
from src.core.exceptions import BaseAPIException, ValidationError
from src.domains.plugins.import_service import PluginImportService
from src.domains.plugins.schemas import (
    PluginComponentKind,
    PluginComponentStatus,
    PluginIssueCode,
)

pytestmark = pytest.mark.unit

_OWNER = uuid4()
_PLUGIN_ROW_ID = uuid4()


def _skill_md(name: str) -> str:
    return f"---\nname: {name}\ndescription: Does something useful.\n---\nBody.\n"


def _manifest(name: str = "my-plugin", **extra: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {"$schema": AGENT_PLUGINS_PLUGIN_SCHEMA_ID, "name": name}
    doc.update(extra)
    return doc


def _mcp_doc(servers: dict[str, Any]) -> dict[str, Any]:
    return {"$schema": AGENT_PLUGINS_MCP_SCHEMA_ID, "mcpServers": servers}


def _plugin_zip(
    manifest: dict[str, Any] | str | None = None,
    skills: dict[str, str] | None = None,
    mcp: dict[str, Any] | str | None = None,
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        if manifest is not None:
            body = manifest if isinstance(manifest, str) else json.dumps(manifest)
            zf.writestr("plugin.json", body)
        for name, md in (skills or {}).items():
            zf.writestr(f"skills/{name}/SKILL.md", md)
        if mcp is not None:
            body = mcp if isinstance(mcp, str) else json.dumps(mcp)
            zf.writestr("mcp.json", body)
    return buf.getvalue()


@pytest.fixture
def scaffold(tmp_path: Path):
    """Service with mocked collaborators and tmp disk roots."""
    db = MagicMock()
    db.commit = AsyncMock()
    svc = PluginImportService(db)

    svc.plugin_repo = MagicMock()
    svc.plugin_repo.get_by_name_for_user = AsyncMock(return_value=None)
    svc.plugin_repo.count_for_user = AsyncMock(return_value=0)
    plugin_row = MagicMock(id=_PLUGIN_ROW_ID)
    plugin_row.name = "my-plugin"
    svc.plugin_repo.create = AsyncMock(return_value=plugin_row)
    svc.plugin_repo.update = AsyncMock()
    svc.plugin_repo.delete = AsyncMock()

    settings = MagicMock(
        plugins_users_path=str(tmp_path / "plugins"),
        skills_users_path=str(tmp_path / "skills"),
        plugins_max_per_user=10,
        plugins_max_file_size_kb=512,
        plugins_zip_max_decompressed_kb=8192,
        plugins_zip_max_files=256,
        skills_max_per_user=20,
        mcp_user_max_servers_per_user=20,
    )

    skill_importer = MagicMock()
    skill_importer.import_directory = AsyncMock(side_effect=lambda d, **kw: {"name": Path(d).name})
    skill_importer.owned_skill_names = AsyncMock(return_value=set())

    mcp_service = MagicMock()
    mcp_service.repository = MagicMock()
    mcp_service.repository.count_for_user = AsyncMock(return_value=0)
    mcp_service.repository.get_by_name_for_user = AsyncMock(return_value=None)
    mcp_service.repository.get_by_plugin_id = AsyncMock(return_value=[])
    mcp_service.create_server = AsyncMock(return_value=MagicMock(id=uuid4()))
    mcp_service.delete_server = AsyncMock()

    skill_repo = MagicMock()
    skill_repo.get_by_plugin_id = AsyncMock(return_value=[])

    pref = MagicMock()
    pref.delete_skill = AsyncMock()

    cache = MagicMock()
    cache.invalidate_and_reload = AsyncMock()

    patches = (
        patch("src.core.config.get_settings", return_value=settings),
        patch(
            "src.domains.skills.import_service.SkillImportService",
            return_value=skill_importer,
        ),
        patch("src.domains.user_mcp.service.UserMCPServerService", return_value=mcp_service),
        patch("src.domains.skills.repository.SkillRepository", return_value=skill_repo),
        patch(
            "src.domains.skills.preference_service.SkillPreferenceService",
            return_value=pref,
        ),
        patch("src.domains.skills.cache.SkillsCache", cache),
    )
    return SimpleNamespaceLike(
        svc=svc,
        db=db,
        settings=settings,
        skill_importer=skill_importer,
        mcp_service=mcp_service,
        skill_repo=skill_repo,
        pref=pref,
        cache=cache,
        patches=patches,
        tmp_path=tmp_path,
    )


class SimpleNamespaceLike:
    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


def _run(scaffold, coro):
    """Await a service call under the full patch stack."""

    async def _inner():
        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in scaffold.patches:
                stack.enter_context(p)
            return await coro()

    return _inner()


class TestInstallHappyPath:
    @pytest.mark.asyncio
    async def test_full_plugin_installs_and_reports_every_component(self, scaffold) -> None:
        content = _plugin_zip(
            manifest=_manifest(version="1.2.0", description="Test plugin"),
            skills={"alpha": _skill_md("alpha"), "beta": _skill_md("beta")},
            mcp=_mcp_doc(
                {
                    "api": {"type": "streamable-http", "url": "https://api.example.com/mcp"},
                    "local": {"type": "stdio", "command": "./bin/x"},
                    "legacy": {"type": "sse", "url": "https://legacy.example.com/sse"},
                }
            ),
        )

        report = await _run(
            scaffold,
            lambda: scaffold.svc.import_upload(content, owner_id=_OWNER),
        )

        by_key = {(c.kind, c.key): c for c in report.components}
        assert (
            by_key[(PluginComponentKind.SKILL, "alpha")].status is PluginComponentStatus.INSTALLED
        )
        assert by_key[(PluginComponentKind.SKILL, "beta")].status is PluginComponentStatus.INSTALLED
        assert (
            by_key[(PluginComponentKind.MCP_SERVER, "api")].status
            is PluginComponentStatus.INSTALLED
        )
        skipped_stdio = by_key[(PluginComponentKind.MCP_SERVER, "local")]
        assert skipped_stdio.status is PluginComponentStatus.SKIPPED
        assert [i.code for i in skipped_stdio.issues] == [
            PluginIssueCode.SERVER_TRANSPORT_UNSUPPORTED
        ]
        skipped_sse = by_key[(PluginComponentKind.MCP_SERVER, "legacy")]
        assert skipped_sse.status is PluginComponentStatus.SKIPPED

        assert report.name == "my-plugin"
        assert report.version == "1.2.0"
        assert report.updated is False
        # Both skills imported with the plugin provenance
        assert scaffold.skill_importer.import_directory.await_count == 2
        for call in scaffold.skill_importer.import_directory.await_args_list:
            assert call.kwargs["plugin_id"] == _PLUGIN_ROW_ID
        # The supported server was created with provenance + prefixed name
        create_kwargs = scaffold.mcp_service.create_server.await_args.kwargs
        assert create_kwargs["plugin_id"] == _PLUGIN_ROW_ID
        assert scaffold.mcp_service.create_server.await_args.args[1].name == "my-plugin:api"
        scaffold.db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_plugin_root_is_persisted_on_disk(self, scaffold) -> None:
        content = _plugin_zip(manifest=_manifest(), skills={"alpha": _skill_md("alpha")})

        await _run(scaffold, lambda: scaffold.svc.import_upload(content, owner_id=_OWNER))

        root = Path(scaffold.settings.plugins_users_path) / str(_OWNER) / "my-plugin"
        assert (root / "plugin.json").is_file()
        assert (root / "skills" / "alpha" / "SKILL.md").is_file()

    @pytest.mark.asyncio
    async def test_skills_only_plugin_is_valid(self, scaffold) -> None:
        content = _plugin_zip(manifest=_manifest(), skills={"alpha": _skill_md("alpha")})

        report = await _run(scaffold, lambda: scaffold.svc.import_upload(content, owner_id=_OWNER))

        assert len(report.components) == 1
        scaffold.mcp_service.create_server.assert_not_awaited()


class TestResilience:
    @pytest.mark.asyncio
    async def test_skill_conflict_is_skipped_others_install(self, scaffold) -> None:
        def _import(d: Path, **kw: Any) -> dict[str, Any]:
            if Path(d).name == "beta":
                raise BaseAPIException(status_code=status.HTTP_409_CONFLICT, detail="name conflict")
            return {"name": Path(d).name}

        scaffold.skill_importer.import_directory = AsyncMock(side_effect=_import)
        content = _plugin_zip(
            manifest=_manifest(), skills={"alpha": _skill_md("alpha"), "beta": _skill_md("beta")}
        )

        report = await _run(scaffold, lambda: scaffold.svc.import_upload(content, owner_id=_OWNER))

        by_key = {c.key: c for c in report.components}
        assert by_key["alpha"].status is PluginComponentStatus.INSTALLED
        assert by_key["beta"].status is PluginComponentStatus.SKIPPED
        assert [i.code for i in by_key["beta"].issues] == [PluginIssueCode.SKILL_NAME_CONFLICT]

    @pytest.mark.asyncio
    async def test_invalid_skill_is_skipped_with_reason(self, scaffold) -> None:
        scaffold.skill_importer.import_directory = AsyncMock(
            side_effect=ValidationError("bad frontmatter")
        )
        content = _plugin_zip(manifest=_manifest(), skills={"broken": _skill_md("broken")})

        report = await _run(scaffold, lambda: scaffold.svc.import_upload(content, owner_id=_OWNER))

        [component] = report.components
        assert component.status is PluginComponentStatus.SKIPPED
        assert [i.code for i in component.issues] == [PluginIssueCode.SKILL_INVALID]

    @pytest.mark.asyncio
    async def test_unparseable_mcp_json_disables_mcp_but_skills_install(self, scaffold) -> None:
        content = _plugin_zip(
            manifest=_manifest(), skills={"alpha": _skill_md("alpha")}, mcp="{not json"
        )

        report = await _run(scaffold, lambda: scaffold.svc.import_upload(content, owner_id=_OWNER))

        assert [c.key for c in report.components] == ["alpha"]
        assert any(w.code == PluginIssueCode.MCP_CONFIG_INVALID for w in report.warnings)
        scaffold.mcp_service.create_server.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_server_name_collision_is_skipped_with_reason(self, scaffold) -> None:
        scaffold.mcp_service.create_server = AsyncMock(
            side_effect=ValidationError("An MCP server named 'my-plugin:api' already exists")
        )
        content = _plugin_zip(
            manifest=_manifest(),
            mcp=_mcp_doc({"api": {"type": "streamable-http", "url": "https://x.example/mcp"}}),
        )

        report = await _run(scaffold, lambda: scaffold.svc.import_upload(content, owner_id=_OWNER))

        [component] = report.components
        assert component.status is PluginComponentStatus.SKIPPED
        assert [i.code for i in component.issues] == [PluginIssueCode.SERVER_CREATE_FAILED]


class TestFatalRejections:
    @pytest.mark.asyncio
    async def test_invalid_manifest_rejects_everything(self, scaffold) -> None:
        content = _plugin_zip(manifest={"name": "no-schema"}, skills={"alpha": _skill_md("alpha")})

        with pytest.raises(BaseAPIException):
            await _run(scaffold, lambda: scaffold.svc.import_upload(content, owner_id=_OWNER))

        scaffold.skill_importer.import_directory.assert_not_awaited()
        scaffold.plugin_repo_create_never = scaffold.svc.plugin_repo.create
        scaffold.plugin_repo_create_never.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unparseable_manifest_rejects_everything(self, scaffold) -> None:
        content = _plugin_zip(manifest="{not json")

        with pytest.raises(BaseAPIException):
            await _run(scaffold, lambda: scaffold.svc.import_upload(content, owner_id=_OWNER))

    @pytest.mark.asyncio
    async def test_oversized_upload_rejected(self, scaffold) -> None:
        scaffold.settings.plugins_max_file_size_kb = 1

        with pytest.raises(BaseAPIException):
            await _run(
                scaffold,
                lambda: scaffold.svc.import_upload(b"0" * 2048, owner_id=_OWNER),
            )

    @pytest.mark.asyncio
    async def test_plugin_quota_pre_checked(self, scaffold) -> None:
        scaffold.svc.plugin_repo.count_for_user = AsyncMock(return_value=10)
        content = _plugin_zip(manifest=_manifest())

        with pytest.raises(BaseAPIException):
            await _run(scaffold, lambda: scaffold.svc.import_upload(content, owner_id=_OWNER))

    @pytest.mark.asyncio
    async def test_skill_quota_pre_checked_before_any_write(self, scaffold) -> None:
        scaffold.skill_importer.owned_skill_names = AsyncMock(
            return_value={f"s{i}" for i in range(20)}
        )
        content = _plugin_zip(manifest=_manifest(), skills={"alpha": _skill_md("alpha")})

        with pytest.raises(BaseAPIException):
            await _run(scaffold, lambda: scaffold.svc.import_upload(content, owner_id=_OWNER))

        scaffold.skill_importer.import_directory.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_server_quota_pre_checked_before_any_write(self, scaffold) -> None:
        scaffold.mcp_service.repository.count_for_user = AsyncMock(return_value=20)
        content = _plugin_zip(
            manifest=_manifest(),
            mcp=_mcp_doc({"api": {"type": "streamable-http", "url": "https://x.example/mcp"}}),
        )

        with pytest.raises(BaseAPIException):
            await _run(scaffold, lambda: scaffold.svc.import_upload(content, owner_id=_OWNER))

        scaffold.mcp_service.create_server.assert_not_awaited()


class TestUpdateFlow:
    @pytest.mark.asyncio
    async def test_reimport_updates_and_removes_dropped_components(self, scaffold) -> None:
        existing_row = MagicMock(id=_PLUGIN_ROW_ID)
        existing_row.name = "my-plugin"
        scaffold.svc.plugin_repo.get_by_name_for_user = AsyncMock(return_value=existing_row)
        old_skill = MagicMock()
        old_skill.name = "gone"
        scaffold.skill_repo.get_by_plugin_id = AsyncMock(return_value=[old_skill])
        old_server = MagicMock(id=uuid4())
        old_server.name = "my-plugin:dropped"
        scaffold.mcp_service.repository.get_by_plugin_id = AsyncMock(return_value=[old_server])

        content = _plugin_zip(
            manifest=_manifest(version="2.0.0"), skills={"alpha": _skill_md("alpha")}
        )

        report = await _run(scaffold, lambda: scaffold.svc.import_upload(content, owner_id=_OWNER))

        assert report.updated is True
        by_key = {(c.kind, c.key): c for c in report.components}
        assert by_key[(PluginComponentKind.SKILL, "gone")].status is PluginComponentStatus.REMOVED
        assert (
            by_key[(PluginComponentKind.MCP_SERVER, "my-plugin:dropped")].status
            is PluginComponentStatus.REMOVED
        )
        scaffold.pref.delete_skill.assert_awaited_once_with("gone")
        scaffold.mcp_service.delete_server.assert_awaited_once()
        assert scaffold.mcp_service.delete_server.await_args.kwargs["allow_plugin_owned"] is True
        scaffold.svc.plugin_repo.create.assert_not_awaited()


class TestUpdateFlowEdgeCases:
    @pytest.mark.asyncio
    async def test_frontmatter_name_governs_removal_not_directory_name(self, scaffold) -> None:
        """A skill whose directory name differs from its frontmatter name must
        NOT be removed by the update flow — removal is keyed on the installed
        (frontmatter) identity, or the update would destroy the very skill it
        just upserted."""
        existing_row = MagicMock(id=_PLUGIN_ROW_ID)
        existing_row.name = "my-plugin"
        scaffold.svc.plugin_repo.get_by_name_for_user = AsyncMock(return_value=existing_row)
        prev_skill = MagicMock()
        prev_skill.name = "real-name"
        scaffold.skill_repo.get_by_plugin_id = AsyncMock(return_value=[prev_skill])

        # Directory is "dir-name" but the frontmatter declares "real-name".
        content = _plugin_zip(
            manifest=_manifest(version="2.0.0"),
            skills={"dir-name": _skill_md("real-name")},
        )
        scaffold.skill_importer.import_directory = AsyncMock(return_value={"name": "real-name"})

        report = await _run(scaffold, lambda: scaffold.svc.import_upload(content, owner_id=_OWNER))

        assert not any(
            c.status is PluginComponentStatus.REMOVED for c in report.components
        ), "the updated skill must never be removed"
        scaffold.pref.delete_skill.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_removal_only_update_reloads_the_skills_cache(self, scaffold) -> None:
        """An update that only REMOVES skills must reload the cache itself —
        no per-skill _finalize runs to do it."""
        existing_row = MagicMock(id=_PLUGIN_ROW_ID)
        existing_row.name = "my-plugin"
        scaffold.svc.plugin_repo.get_by_name_for_user = AsyncMock(return_value=existing_row)
        prev_skill = MagicMock()
        prev_skill.name = "gone"
        scaffold.skill_repo.get_by_plugin_id = AsyncMock(return_value=[prev_skill])

        content = _plugin_zip(manifest=_manifest(version="2.0.0"))

        report = await _run(scaffold, lambda: scaffold.svc.import_upload(content, owner_id=_OWNER))

        assert any(c.status is PluginComponentStatus.REMOVED for c in report.components)
        scaffold.cache.invalidate_and_reload.assert_awaited()


class TestUninstall:
    @pytest.mark.asyncio
    async def test_uninstall_removes_components_rows_and_disk(self, scaffold) -> None:
        plugin_row = MagicMock(id=_PLUGIN_ROW_ID, user_id=_OWNER)
        plugin_row.name = "my-plugin"
        scaffold.svc.plugin_repo.get_by_id = AsyncMock(return_value=plugin_row)

        skill = MagicMock()
        skill.name = "alpha"
        scaffold.skill_repo.get_by_plugin_id = AsyncMock(return_value=[skill])
        server = MagicMock(id=uuid4())
        scaffold.mcp_service.repository.get_by_plugin_id = AsyncMock(return_value=[server])

        # Materialize disk trees the uninstall must remove
        skill_dir = Path(scaffold.settings.skills_users_path) / str(_OWNER) / "alpha"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("x", encoding="utf-8")
        plugin_root = Path(scaffold.settings.plugins_users_path) / str(_OWNER) / "my-plugin"
        plugin_root.mkdir(parents=True)
        (plugin_root / "plugin.json").write_text("{}", encoding="utf-8")

        await _run(scaffold, lambda: scaffold.svc.uninstall(_PLUGIN_ROW_ID, owner_id=_OWNER))

        scaffold.pref.delete_skill.assert_awaited_once_with("alpha")
        scaffold.mcp_service.delete_server.assert_awaited_once()
        assert scaffold.mcp_service.delete_server.await_args.kwargs["allow_plugin_owned"] is True
        scaffold.svc.plugin_repo.delete.assert_awaited_once_with(plugin_row)
        assert not skill_dir.exists()
        assert not plugin_root.exists()
        scaffold.db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_uninstall_wrong_owner_is_not_found(self, scaffold) -> None:
        plugin_row = MagicMock(id=_PLUGIN_ROW_ID, user_id=uuid4())
        scaffold.svc.plugin_repo.get_by_id = AsyncMock(return_value=plugin_row)

        with pytest.raises(BaseAPIException):
            await _run(scaffold, lambda: scaffold.svc.uninstall(_PLUGIN_ROW_ID, owner_id=_OWNER))
