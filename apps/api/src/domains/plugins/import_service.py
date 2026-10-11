"""Agent Plugins install / update / uninstall orchestrator (ADR-225).

Composes the already-hardened layers — plugin staging (S3 guards), manifest
and mcp.json validation, the skills ``import_directory`` pipeline (S1-S5 +
atomic per-skill swap) and the user MCP service — into the plugin lifecycle:

- §11.3 resilience: per-component failures never abort the install; every
  outcome (installed / updated / skipped / removed, with taxonomy reasons)
  lands in the import report — LIA's anti-false-success doctrine;
- quotas (plugins, skills, MCP servers) are pre-checked globally BEFORE any
  write, so an install is never left half-done by a mid-flight cap;
- update = re-import of the same name: components upsert within their
  provenance, components the new version dropped are removed;
- uninstall removes the plugin's components (rows + disk) and its root
  (arbitrage F: the only way plugin components leave).
"""

import json
import tempfile
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import AGENT_PLUGINS_SPEC_VERSION
from src.core.exceptions import AuthorizationError, BaseAPIException, ValidationError
from src.domains.plugins.exceptions import (
    raise_plugin_file_too_large,
    raise_plugin_invalid_package,
    raise_plugin_quota_exceeded,
)
from src.domains.plugins.import_hooks import PluginImportHooks
from src.domains.plugins.manifest import validate_plugin_manifest
from src.domains.plugins.mcp_config import validate_mcp_config
from src.domains.plugins.repository import UserPluginRepository
from src.domains.plugins.schemas import (
    McpConfigValidationResult,
    McpServerStatus,
    McpServerValidation,
    PluginComponentKind,
    PluginComponentReport,
    PluginComponentStatus,
    PluginImportReport,
    PluginIssue,
    PluginIssueCode,
    PluginManifest,
)
from src.domains.plugins.staging import stage_plugin_zip
from src.domains.skills.import_disk import read_disk_step
from src.domains.skills.models import SkillProvenance
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.plugins.models import UserPlugin
    from src.domains.user_mcp.models import UserMCPServer

logger = get_logger(__name__)

# UserMCPServer.name column budget (String(100)); plugin server names are
# composed as "<plugin>:<key>" and must fit it.
_MCP_SERVER_NAME_MAX = 100


def _server_display_name(plugin_name: str, server_key: str) -> str:
    """Compose the per-user unique server name for a plugin's mcp.json entry."""
    return f"{plugin_name}:{server_key}"


class PluginImportService:
    """Hardened, per-component-transactional plugin lifecycle pipeline."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.plugin_repo = UserPluginRepository(db)

    # ------------------------------------------------------------------
    # Install / update
    # ------------------------------------------------------------------

    async def import_upload(
        self, content: bytes, *, owner_id: UUID, hooks: PluginImportHooks | None = None
    ) -> PluginImportReport:
        """Install or update a plugin from an uploaded zip package.

        Args:
            content: Raw uploaded bytes.
            owner_id: Importing user's id.

        Returns:
            The full per-component import report (§11.3 SHOULD-report).

        Raises:
            BaseAPIException / ValidationError: on size, package, manifest or
                quota violations (all pre-checked before any write).
        """
        from src.core.config import get_settings

        settings = get_settings()
        if len(content) > settings.plugins_max_file_size_kb * 1024:
            raise_plugin_file_too_large(len(content), settings.plugins_max_file_size_kb)

        with tempfile.TemporaryDirectory(prefix="plugin_import_") as staging_root:
            plugin_root = await read_disk_step(
                partial(stage_plugin_zip, content, Path(staging_root), settings)
            )
            return await self._install_from_root(
                plugin_root,
                owner_id=owner_id,
                settings=settings,
                hooks=hooks or PluginImportHooks(),
            )

    async def _install_from_root(
        self, plugin_root: Path, *, owner_id: UUID, settings: Any, hooks: PluginImportHooks
    ) -> PluginImportReport:
        """Validate a staged plugin root, then install/update its components."""
        from src.domains.skills import import_service as skills_import
        from src.domains.skills import preference_service as skills_pref
        from src.domains.user_mcp import service as user_mcp_service

        # Blocking file reads (manifest, discovery, mcp.json, frontmatter
        # pre-parse) run off the event loop, like the skills pipeline (CA-4).
        manifest, warnings = await read_disk_step(partial(self._load_manifest, plugin_root))
        skill_dirs = await read_disk_step(partial(self._discover_skill_dirs, plugin_root, warnings))
        mcp_result = await read_disk_step(partial(self._load_mcp_config, plugin_root, warnings))
        supported_servers = [
            s
            for s in (mcp_result.servers if mcp_result else [])
            if s.status is McpServerStatus.SUPPORTED
        ]

        skill_importer = skills_import.SkillImportService(self.db)
        mcp_service = user_mcp_service.UserMCPServerService(self.db)
        pref_service = skills_pref.SkillPreferenceService(self.db)

        # Existing installation? (update flow) + plugin quota for new installs.
        existing = await self.plugin_repo.get_by_name_for_user(owner_id, manifest.name)
        updated = existing is not None
        await self._check_plugin_quota(existing, owner_id, settings)
        prev_skills, prev_servers = await self._previous_components(existing, owner_id=owner_id)
        prev_server_names = {s.name for s in prev_servers}

        # Installed identity is the FRONTMATTER name (§7.1 discovery only keys
        # on the directory) — quotas and the update-flow removal set must be
        # keyed on it, or an update would remove the skill it just upserted
        # whenever a directory name differs from the declared name.
        incoming_skill_names = await read_disk_step(partial(self._incoming_skill_names, skill_dirs))
        incoming_server_names = {
            _server_display_name(manifest.name, s.key) for s in supported_servers
        }

        # ADR-225: quotas pre-checked globally BEFORE any write.
        await self._pre_check_component_quotas(
            skill_importer,
            mcp_service,
            owner_id=owner_id,
            incoming_skill_names=incoming_skill_names,
            incoming_server_names=incoming_server_names,
            prev_server_names=prev_server_names,
            settings=settings,
        )

        if hooks.before_write is not None:
            await hooks.before_write(self.db)
        plugin_row = await self._upsert_plugin_row(existing, manifest, owner_id)
        hooks.plugin_written(plugin_row)

        components: list[PluginComponentReport] = []
        components.extend(
            self._report_unsupported_servers(mcp_result.servers if mcp_result else [])
        )
        components.extend(
            await self._install_skills(
                skill_dirs,
                skill_importer,
                owner_id=owner_id,
                plugin_id=plugin_row.id,
                prev_skill_names=set(prev_skills),
                hooks=hooks,
            )
        )
        components.extend(
            await self._install_servers(
                supported_servers,
                mcp_service,
                owner_id=owner_id,
                plugin_row=plugin_row,
                manifest=manifest,
                prev_server_names=prev_server_names,
                hooks=hooks,
            )
        )
        live_root = Path(settings.plugins_users_path) / str(owner_id) / manifest.name
        from src.domains.plugins.dropped_files import retain_dropped_files
        from src.domains.plugins.root_commit import commit_plugin_root

        if hooks.before_drop is not None:
            await hooks.before_drop(self.db, components)
        async with retain_dropped_files(
            self.db,
            owner_id,
            Path(settings.skills_users_path),
            set(prev_skills) - set(incoming_skill_names),
            after_stage=hooks.after_drop_stage,
        ) as dropped_files:
            removed_components = await self._remove_dropped_components(
                pref_service,
                mcp_service,
                owner_id=owner_id,
                prev_skills=prev_skills,
                incoming_skill_names=set(incoming_skill_names),
                prev_servers=prev_servers,
                incoming_server_names=incoming_server_names,
                settings=settings,
            )

            root_result = await commit_plugin_root(
                self.db,
                plugin_root,
                live_root,
                before_commit=partial(hooks.check_commit, self.db),
                after_stage=hooks.after_root_stage,
                after_commit=partial(hooks.root_committed, plugin_row),
            )
        components.extend(removed_components)

        # A removal-only update runs no per-skill _finalize, so nothing else
        # reloads the skills cache — do it here when a skill was removed.
        if any(c.kind is PluginComponentKind.SKILL for c in removed_components):
            from src.domains.skills import cache as skills_cache

            await skills_cache.SkillsCache.invalidate_and_reload()

        report = PluginImportReport(
            plugin_id=str(plugin_row.id),
            name=manifest.name,
            version=manifest.version,
            description=manifest.description,
            updated=updated,
            components=components,
            warnings=warnings,
            file_cleanup_pending=root_result.cleanup_pending or dropped_files.cleanup_pending,
        )
        self._log_import_summary(report, owner_id)
        return report

    async def _check_plugin_quota(
        self, existing: UserPlugin | None, owner_id: UUID, settings: Any
    ) -> None:
        """Enforce the installed-plugin cap — updates never re-count."""
        if existing is not None:
            return
        installed_count = await self.plugin_repo.count_for_user(owner_id)
        if installed_count >= settings.plugins_max_per_user:
            raise_plugin_quota_exceeded(settings.plugins_max_per_user)

    async def _previous_components(
        self, existing: UserPlugin | None, *, owner_id: UUID
    ) -> tuple[dict[str, UUID], list[UserMCPServer]]:
        """Components of the existing installation (empty on a fresh install).

        Skills come back as name → row id: a removal deletes the ROW, never a
        name, which since ADR-327 other accounts may hold too.
        """
        if existing is None:
            return {}, []
        from src.domains.plugins.group_scope import load_plugin_group

        try:
            group = await load_plugin_group(self.db, owner_id, existing.id)
        except ValueError as exc:
            raise ValidationError("Plugin component ownership is inconsistent") from exc
        return {skill.name: skill.id for skill in group.skills}, list(group.servers)

    @staticmethod
    def _log_import_summary(report: PluginImportReport, owner_id: UUID) -> None:
        """One structured line per import — counters only, no PII."""
        logger.info(
            "plugin_import_completed",
            plugin_name=report.name,
            user_id=str(owner_id),
            updated=report.updated,
            installed=sum(
                1 for c in report.components if c.status is PluginComponentStatus.INSTALLED
            ),
            skipped=sum(1 for c in report.components if c.status is PluginComponentStatus.SKIPPED),
            removed=sum(1 for c in report.components if c.status is PluginComponentStatus.REMOVED),
            warning_count=len(report.warnings),
        )

    # ------------------------------------------------------------------
    # Manifest / component discovery
    # ------------------------------------------------------------------

    def _load_manifest(self, plugin_root: Path) -> tuple[PluginManifest, list[PluginIssue]]:
        """Load and validate plugin.json; fatal violations reject the plugin."""
        try:
            raw = json.loads((plugin_root / "plugin.json").read_text("utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise_plugin_invalid_package(f"plugin.json is not valid JSON: {exc}")
        result = validate_plugin_manifest(raw)
        if not result.valid or result.manifest is None:
            details = "; ".join(
                f"{issue.code.value}" + (f" ({issue.field})" if issue.field else "")
                for issue in result.errors
            )
            raise_plugin_invalid_package(f"plugin.json violates the manifest contract: {details}")
        return result.manifest, list(result.warnings)

    def _incoming_skill_names(self, skill_dirs: list[Path]) -> list[str]:
        """Frontmatter names of the incoming skills (fallback: directory name).

        The frontmatter name is the identity the pipeline installs under; a
        directory whose SKILL.md cannot be parsed keeps its directory name —
        its import will fail and be reported per-component anyway.
        """
        from src.domains.skills.import_service import _parse_frontmatter_name

        names: list[str] = []
        for skill_dir in skill_dirs:
            try:
                text = (skill_dir / "SKILL.md").read_text("utf-8-sig")
                names.append(_parse_frontmatter_name(text))
            except Exception:  # noqa: BLE001 - tolerant pre-parse, import reports later
                names.append(skill_dir.name)
        return names

    def _discover_skill_dirs(self, plugin_root: Path, warnings: list[PluginIssue]) -> list[Path]:
        """§7.1: immediate children of skills/ holding a regular SKILL.md."""
        skills_location = plugin_root / "skills"
        if not skills_location.exists():
            return []
        if not skills_location.is_dir():
            warnings.append(
                PluginIssue(
                    code=PluginIssueCode.COMPONENT_LOCATION_INVALID,
                    field="skills",
                    detail="skills exists but is not a directory (§6.2)",
                )
            )
            return []
        return sorted(
            child
            for child in skills_location.iterdir()
            if child.is_dir() and (child / "SKILL.md").is_file()
        )

    def _load_mcp_config(
        self, plugin_root: Path, warnings: list[PluginIssue]
    ) -> McpConfigValidationResult | None:
        """§7.2.2 rule 2: a config-level violation disables MCP, never the rest."""
        mcp_location = plugin_root / "mcp.json"
        if not mcp_location.exists():
            return None
        if not mcp_location.is_file():
            warnings.append(
                PluginIssue(
                    code=PluginIssueCode.COMPONENT_LOCATION_INVALID,
                    field="mcp.json",
                    detail="mcp.json exists but is not a regular file (§6.2)",
                )
            )
            return None
        try:
            raw = json.loads(mcp_location.read_text("utf-8-sig"))
        except (OSError, ValueError) as exc:
            warnings.append(
                PluginIssue(
                    code=PluginIssueCode.MCP_CONFIG_INVALID,
                    field="mcp.json",
                    detail=f"not valid JSON: {exc}",
                )
            )
            return None
        result = validate_mcp_config(raw)
        if not result.valid:
            warnings.extend(result.issues)
            return None
        return result

    # ------------------------------------------------------------------
    # Quota pre-checks (before any write)
    # ------------------------------------------------------------------

    async def _pre_check_component_quotas(
        self,
        skill_importer: Any,
        mcp_service: Any,
        *,
        owner_id: UUID,
        incoming_skill_names: list[str],
        incoming_server_names: set[str],
        prev_server_names: set[str],
        settings: Any,
    ) -> None:
        """Reject the whole import when a quota would be crossed mid-install."""
        owned = await skill_importer.owned_skill_names(owner_id)
        if len(owned | set(incoming_skill_names)) > settings.skills_max_per_user:
            raise_plugin_invalid_package(
                f"plugin skills would exceed the {settings.skills_max_per_user}-skill quota"
            )

        current_servers = await mcp_service.repository.count_for_user(owner_id)
        new_servers = len(incoming_server_names - prev_server_names)
        if current_servers + new_servers > settings.mcp_user_max_servers_per_user:
            raise_plugin_invalid_package(
                "plugin MCP servers would exceed the "
                f"{settings.mcp_user_max_servers_per_user}-server quota"
            )

    # ------------------------------------------------------------------
    # Component installation
    # ------------------------------------------------------------------

    async def _upsert_plugin_row(
        self, existing: UserPlugin | None, manifest: PluginManifest, owner_id: UUID
    ) -> UserPlugin:
        """Create the plugin row, or refresh the metadata of an existing one."""
        row_data = {
            "name": manifest.name,
            "version": manifest.version,
            "description": manifest.description,
            "manifest": manifest.model_dump(by_alias=True, exclude_none=True),
            "spec_version": AGENT_PLUGINS_SPEC_VERSION,
        }
        if existing is not None:
            await self.plugin_repo.update(existing, row_data)
            return existing
        return await self.plugin_repo.create({"user_id": owner_id, **row_data})

    async def _install_skills(
        self,
        skill_dirs: list[Path],
        skill_importer: Any,
        *,
        owner_id: UUID,
        plugin_id: UUID,
        prev_skill_names: set[str],
        hooks: PluginImportHooks,
    ) -> list[PluginComponentReport]:
        """Install each discovered skill; failures are per-skill, never fatal."""
        reports: list[PluginComponentReport] = []
        for skill_dir in skill_dirs:
            try:
                result = await skill_importer.import_directory(
                    skill_dir,
                    owner_id=owner_id,
                    provenance=SkillProvenance.PLUGIN,
                    plugin_id=plugin_id,
                    before_swap=partial(hooks.check_skill_swap, skill_dir),
                    before_commit=hooks.before_commit,
                    after_commit=hooks.after_skill_commit,
                )
                installed_name = str(result["name"])
                reports.append(
                    PluginComponentReport(
                        kind=PluginComponentKind.SKILL,
                        key=installed_name,
                        status=(
                            PluginComponentStatus.UPDATED
                            if installed_name in prev_skill_names
                            else PluginComponentStatus.INSTALLED
                        ),
                    )
                )
            except AuthorizationError:
                raise
            except BaseAPIException as exc:
                is_conflict = getattr(exc, "status_code", None) == status.HTTP_409_CONFLICT
                reports.append(
                    PluginComponentReport(
                        kind=PluginComponentKind.SKILL,
                        key=skill_dir.name,
                        status=PluginComponentStatus.SKIPPED,
                        issues=[
                            PluginIssue(
                                code=(
                                    PluginIssueCode.SKILL_NAME_CONFLICT
                                    if is_conflict
                                    else PluginIssueCode.SKILL_INVALID
                                ),
                                field=skill_dir.name,
                                detail=str(getattr(exc, "detail", exc)),
                            )
                        ],
                    )
                )
        return reports

    def _report_unsupported_servers(
        self, servers: list[McpServerValidation]
    ) -> list[PluginComponentReport]:
        """Turn non-supported mcp.json entries into skipped-component reports."""
        return [
            PluginComponentReport(
                kind=PluginComponentKind.MCP_SERVER,
                key=server.key,
                status=PluginComponentStatus.SKIPPED,
                issues=list(server.issues),
            )
            for server in servers
            if server.status is not McpServerStatus.SUPPORTED
        ]

    async def _install_servers(
        self,
        supported_servers: list[McpServerValidation],
        mcp_service: Any,
        *,
        owner_id: UUID,
        plugin_row: UserPlugin,
        manifest: PluginManifest,
        prev_server_names: set[str],
        hooks: PluginImportHooks,
    ) -> list[PluginComponentReport]:
        """Create/update the plugin's streamable-http servers, one by one."""
        from src.domains.user_mcp.schemas import UserMCPServerCreate, UserMCPServerUpdate

        reports: list[PluginComponentReport] = []
        for server in supported_servers:
            name = _server_display_name(manifest.name, server.key)
            if len(name) > _MCP_SERVER_NAME_MAX:
                reports.append(
                    PluginComponentReport(
                        kind=PluginComponentKind.MCP_SERVER,
                        key=server.key,
                        status=PluginComponentStatus.SKIPPED,
                        issues=[
                            PluginIssue(
                                code=PluginIssueCode.SERVER_ENTRY_INVALID,
                                field=server.key,
                                detail=f"composed server name exceeds {_MCP_SERVER_NAME_MAX} chars",
                            )
                        ],
                    )
                )
                continue

            existing_server = await mcp_service.repository.get_by_name_for_user(owner_id, name)
            if existing_server is not None and existing_server.plugin_id != plugin_row.id:
                reports.append(
                    PluginComponentReport(
                        kind=PluginComponentKind.MCP_SERVER,
                        key=server.key,
                        status=PluginComponentStatus.SKIPPED,
                        issues=[
                            PluginIssue(
                                code=PluginIssueCode.SERVER_NAME_CONFLICT,
                                field=server.key,
                                detail=f"a server named '{name}' already exists",
                            )
                        ],
                    )
                )
                continue

            try:
                if existing_server is None:
                    refreshed = await mcp_service.create_server(
                        owner_id,
                        UserMCPServerCreate(name=name, url=server.url or ""),
                        plugin_id=plugin_row.id,
                        extra_headers=dict(server.headers) or None,
                        before_write=partial(hooks.check_server_write, name, None),
                    )
                    outcome = PluginComponentStatus.INSTALLED
                else:
                    # Reuse the original ownership, SSRF and pool invalidation seam.
                    refreshed = await mcp_service.update_server(
                        existing_server.id,
                        owner_id,
                        UserMCPServerUpdate(url=server.url or ""),
                        before_write=partial(hooks.check_server_write, name, existing_server.id),
                    )
                    await mcp_service.repository.update(
                        refreshed, {"extra_headers": dict(server.headers) or None}
                    )
                    outcome = PluginComponentStatus.UPDATED
                hooks.server_written(refreshed)
                reports.append(
                    PluginComponentReport(
                        kind=PluginComponentKind.MCP_SERVER,
                        key=server.key,
                        status=outcome,
                    )
                )
            except ValidationError as exc:
                reports.append(
                    PluginComponentReport(
                        kind=PluginComponentKind.MCP_SERVER,
                        key=server.key,
                        status=PluginComponentStatus.SKIPPED,
                        issues=[
                            PluginIssue(
                                code=PluginIssueCode.SERVER_CREATE_FAILED,
                                field=server.key,
                                detail=str(getattr(exc, "detail", exc)),
                            )
                        ],
                    )
                )
        return reports

    async def _remove_dropped_components(
        self,
        pref_service: Any,
        mcp_service: Any,
        *,
        owner_id: UUID,
        prev_skills: dict[str, UUID],
        incoming_skill_names: set[str],
        prev_servers: list[Any],
        incoming_server_names: set[str],
        settings: Any,
    ) -> list[PluginComponentReport]:
        """Update flow: remove components the new plugin version dropped.

        Removal is keyed on the INCOMING package contents, never on install
        success — a skill whose new version failed to import keeps its
        retained previous version (per-skill atomicity) and is reported
        skipped, not removed.
        """
        reports: list[PluginComponentReport] = []
        for name in sorted(set(prev_skills) - incoming_skill_names):
            await pref_service.delete_skill(prev_skills[name])
            reports.append(
                PluginComponentReport(
                    kind=PluginComponentKind.SKILL,
                    key=name,
                    status=PluginComponentStatus.REMOVED,
                )
            )
        for server in prev_servers:
            if server.name in incoming_server_names:
                continue
            await mcp_service.delete_server(server.id, owner_id, allow_plugin_owned=True)
            reports.append(
                PluginComponentReport(
                    kind=PluginComponentKind.MCP_SERVER,
                    key=server.name,
                    status=PluginComponentStatus.REMOVED,
                )
            )
        return reports

    # ------------------------------------------------------------------
    # Uninstall / listing
    # ------------------------------------------------------------------

    async def uninstall(self, plugin_id: UUID, *, owner_id: UUID) -> None:
        """Remove a plugin and every component it installed (arbitrage F).

        Raises:
            ResourceNotFoundError: unknown plugin or not owned by the caller
                (existence is not disclosed).
        """
        from src.domains.plugins.removal import remove_plugin

        await remove_plugin(self.db, owner_id, plugin_id)
        logger.info("plugin_uninstalled", plugin_id=str(plugin_id), user_id=str(owner_id))

    async def list_plugins(self, owner_id: UUID) -> list[UserPlugin]:
        """List installed plugins for a user, ordered by name."""
        return await self.plugin_repo.get_all_for_user(owner_id)
