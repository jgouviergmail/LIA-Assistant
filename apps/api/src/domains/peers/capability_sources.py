"""Detached, exact-owner capability observations; no remote fetch on sharing."""

import asyncio
import json
from dataclasses import dataclass
from functools import partial
from io import BytesIO
from pathlib import Path
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from sqlalchemy import and_, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundError
from src.domains.peers.capability_contracts import (
    CapabilityKind,
    PackageSnapshot,
    PortableMCPConfig,
    PortableServer,
)
from src.domains.peers.capability_overlay import overlay_live_components
from src.domains.peers.capability_package import (
    _snapshot,
    portable_headers,
    refuse_embedded_secrets,
    sanitize_package,
)
from src.domains.plugins.manifest import is_valid_plugin_name, validate_plugin_manifest
from src.domains.plugins.models import UserPlugin
from src.domains.plugins.removal_disk import _checked
from src.domains.skills.archive import (
    _read_checked_resource,
    _resources,
    create_skill_archive,
)
from src.domains.skills.import_service import (
    _parse_frontmatter_name,
    validate_skill_name,
)
from src.domains.skills.models import Skill
from src.domains.user_mcp.models import UserMCPAuthType, UserMCPServer
from src.domains.user_mcp.service import UserMCPServerService
from src.domains.users.models import User


def _plugin_archive(root: Path, account: Path) -> bytes:
    root = _checked(root, account)
    paths = _resources(root, max_files=settings.plugins_zip_max_files, manifest="plugin.json")
    remaining = settings.plugins_zip_max_decompressed_kb * 1024
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for path in paths:
            data = _read_checked_resource(path, root, remaining, partial(_checked, root, account))
            remaining -= len(data)
            info = ZipInfo(path.relative_to(root).as_posix(), date_time=(2000, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, data)
    return buffer.getvalue()


def _validate_snapshot_identity(package: PackageSnapshot) -> None:
    if package.kind is CapabilityKind.SKILL:
        manifest = next(file for file in package.files if file.path == "SKILL.md")
        name = _parse_frontmatter_name(manifest.content.decode("utf-8-sig"))
    else:
        manifest = next(file for file in package.files if file.path == "plugin.json")
        result = validate_plugin_manifest(json.loads(manifest.content))
        if not result.valid or result.manifest is None:
            raise ValueError("Invalid installed plugin manifest")
        name = result.manifest.name
    if name != package.name:
        raise ValueError("Package identity differs from the installed registry")


@dataclass(frozen=True)
class CapabilitySource:
    kind: CapabilityKind
    name: str
    owner_id: UUID | None
    mcp: PortableMCPConfig | None = None
    live_skills: tuple[CapabilitySource, ...] = ()
    live_servers: tuple[PortableServer, ...] = ()

    async def snapshot(self) -> PackageSnapshot:
        return await asyncio.to_thread(self._snapshot)

    def _snapshot(self) -> PackageSnapshot:
        if self.mcp is not None:
            return _snapshot(
                self.kind,
                self.name,
                [],
                [],
                (PortableServer(key=self.name, config=self.mcp),),
            )
        if self.kind is CapabilityKind.SKILL:
            content = create_skill_archive(
                {
                    "name": self.name,
                    "scope": "user" if self.owner_id else "admin",
                    "owner_id": str(self.owner_id) if self.owner_id else None,
                    "source_path": str(
                        (
                            Path(settings.skills_users_path) / str(self.owner_id)
                            if self.owner_id
                            else Path(settings.skills_system_path)
                        )
                        / self.name
                        / "SKILL.md"
                    ),
                }
            )
        else:
            account = Path(settings.plugins_users_path) / str(self.owner_id)
            content = _plugin_archive(account / self.name, account)
        package = sanitize_package(content, self.kind, self.name)
        _validate_snapshot_identity(package)
        if self.kind is CapabilityKind.SKILL:
            return package
        return overlay_live_components(
            package,
            tuple(skill._snapshot() for skill in self.live_skills),
            self.live_servers,
        )


def _mcp_config(db: AsyncSession, row: UserMCPServer) -> PortableMCPConfig:
    public, header, embedded_auth = portable_headers(row.extra_headers or {})
    auth_type = UserMCPAuthType(row.auth_type)
    if embedded_auth is not UserMCPAuthType.NONE:
        if auth_type is not UserMCPAuthType.NONE:
            raise ValueError("Multiple authentication profiles cannot be shared")
        auth_type = embedded_auth
    metadata = UserMCPServerService(db).build_response_metadata(row)
    config = PortableMCPConfig(
        name=row.name,
        url=row.url,
        auth_type=auth_type,
        header_name=header or metadata["header_name"],
        domain_description=row.domain_description,
        timeout_seconds=row.timeout_seconds,
        iterative_mode=row.iterative_mode,
        oauth_scopes=metadata["oauth_scopes"],
        extra_headers=public,
    )
    refuse_embedded_secrets(config.model_dump_json().encode())
    return config


async def load_capability_source(
    db: AsyncSession, sender_id: UUID, kind: CapabilityKind, source_id: UUID
) -> CapabilitySource:
    if kind is CapabilityKind.SKILL:
        actor = await db.get(User, sender_id, populate_existing=True)
        if actor is None or not actor.is_active or actor.deleted_at is not None:
            raise ResourceNotFoundError("capability")
        skill = (
            await db.execute(
                select(Skill).where(
                    Skill.id == source_id,
                    or_(
                        and_(Skill.owner_id == sender_id, Skill.is_system.is_(False)),
                        and_(
                            Skill.owner_id.is_(None),
                            Skill.is_system.is_(True),
                            or_(
                                Skill.admin_enabled.is_(True),
                                literal(actor.is_superuser),
                            ),
                        ),
                    ),
                )
            )
        ).scalar_one_or_none()
        if skill is None:
            raise ResourceNotFoundError("capability")
        validate_skill_name(skill.name)
        return CapabilitySource(kind, skill.name, skill.owner_id)
    if kind is CapabilityKind.PLUGIN:
        plugin = (
            await db.execute(
                select(UserPlugin).where(
                    UserPlugin.id == source_id, UserPlugin.user_id == sender_id
                )
            )
        ).scalar_one_or_none()
        if plugin is None:
            raise ResourceNotFoundError("capability")
        if not is_valid_plugin_name(plugin.name):
            raise ValueError("Invalid installed plugin name")
        live_skills = tuple(
            CapabilitySource(CapabilityKind.SKILL, skill.name, sender_id)
            for skill in await db.scalars(
                select(Skill).where(Skill.plugin_id == plugin.id, Skill.owner_id == sender_id)
            )
        )
        live_servers: list[PortableServer] = []
        prefix = plugin.name + ":"
        for live_server in await db.scalars(
            select(UserMCPServer).where(
                UserMCPServer.plugin_id == plugin.id, UserMCPServer.user_id == sender_id
            )
        ):
            if not live_server.name.startswith(prefix):
                raise ValueError("Plugin server identity differs from its package")
            live_servers.append(
                PortableServer(
                    key=live_server.name[len(prefix) :],
                    config=_mcp_config(db, live_server),
                )
            )
        return CapabilitySource(
            kind,
            plugin.name,
            sender_id,
            live_skills=live_skills,
            live_servers=tuple(live_servers),
        )
    server = (
        await db.execute(
            select(UserMCPServer).where(
                UserMCPServer.id == source_id, UserMCPServer.user_id == sender_id
            )
        )
    ).scalar_one_or_none()
    if server is None:
        raise ResourceNotFoundError("capability")
    return CapabilitySource(kind, server.name, sender_id, _mcp_config(db, server))


async def ensure_source_authorized(
    db: AsyncSession, sender_id: UUID, kind: CapabilityKind, source_id: UUID
) -> None:
    """Publication checks ownership without rereading a whole plugin catalogue."""
    if kind is CapabilityKind.SKILL:
        await load_capability_source(db, sender_id, kind, source_id)
        return
    if kind is CapabilityKind.PLUGIN:
        query = select(UserPlugin.id).where(
            UserPlugin.id == source_id, UserPlugin.user_id == sender_id
        )
    else:
        query = select(UserMCPServer.id).where(
            UserMCPServer.id == source_id, UserMCPServer.user_id == sender_id
        )
    if await db.scalar(query) is None:
        raise ResourceNotFoundError("capability")
