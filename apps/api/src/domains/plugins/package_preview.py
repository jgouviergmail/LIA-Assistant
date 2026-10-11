"""Read-only original manifest/component parsing; package contents remain private."""

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict

from src.core.config import settings
from src.core.constants import AGENT_PLUGINS_SPEC_VERSION, SKILLS_SCRIPT_ALLOWED_EXTENSIONS
from src.domains.plugins.exceptions import raise_plugin_file_too_large
from src.domains.plugins.schemas import McpServerStatus, PluginIssueCode
from src.domains.plugins.staging import stage_plugin_zip
from src.domains.skills.import_disk import read_disk_step
from src.domains.skills.loader import _list_dir
from src.domains.skills.upload_preview import SkillPackageFile

if TYPE_CHECKING:
    from src.domains.plugins.import_service import PluginImportService


class PluginPackageServer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    key: str
    status: McpServerStatus
    transport: str | None
    host: str | None
    has_headers: bool
    issues: tuple[PluginIssueCode, ...]


class PluginPackagePreview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    version: str | None
    description: str | None
    spec_version: str
    skill_names: tuple[str, ...]
    has_scripts: bool
    servers: tuple[PluginPackageServer, ...]
    files: tuple[SkillPackageFile, ...]
    warnings: tuple[PluginIssueCode, ...]


def _preview(service: PluginImportService, content: bytes, staging: Path) -> PluginPackagePreview:
    root = stage_plugin_zip(content, staging, settings)
    manifest, warnings = service._load_manifest(root)
    skill_dirs = service._discover_skill_dirs(root, warnings)
    names = service._incoming_skill_names(skill_dirs)
    mcp = service._load_mcp_config(root, warnings)
    files = tuple(
        SkillPackageFile(path=path.relative_to(root).as_posix(), size=path.stat().st_size)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )
    servers = tuple(
        PluginPackageServer(
            key=server.key,
            status=server.status,
            transport=server.transport,
            host=urlsplit(server.url).hostname if server.url else None,
            has_headers=bool(server.headers),
            issues=tuple(issue.code for issue in server.issues),
        )
        for server in (mcp.servers if mcp is not None else [])
    )
    return PluginPackagePreview(
        name=manifest.name,
        version=manifest.version,
        description=manifest.description,
        spec_version=AGENT_PLUGINS_SPEC_VERSION,
        skill_names=tuple(names),
        has_scripts=any(
            _list_dir(directory / "scripts", SKILLS_SCRIPT_ALLOWED_EXTENSIONS)
            for directory in skill_dirs
        ),
        servers=servers,
        files=files,
        warnings=tuple(issue.code for issue in warnings),
    )


async def preview_plugin_package(
    service: PluginImportService, content: bytes
) -> PluginPackagePreview:
    if len(content) > settings.plugins_max_file_size_kb * 1024:
        raise_plugin_file_too_large(len(content), settings.plugins_max_file_size_kb)
    with tempfile.TemporaryDirectory(prefix="plugin_preview_") as root:
        return await read_disk_step(lambda: _preview(service, content, Path(root)))
