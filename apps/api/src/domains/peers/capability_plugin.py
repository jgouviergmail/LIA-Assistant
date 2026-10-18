"""Receipt-aware plugin hooks retain native per-component installation semantics."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.peers.capability_contracts import CapabilityKind
from src.domains.peers.capability_models import PeerCapabilityComponent
from src.domains.plugins.import_hooks import PluginImportHooks
from src.domains.plugins.import_service import PluginImportService, _server_display_name
from src.domains.plugins.manifest import validate_plugin_manifest
from src.domains.plugins.models import UserPlugin
from src.domains.plugins.root_commit import PluginRootSlot
from src.domains.plugins.schemas import (
    PluginComponentKind,
    PluginComponentStatus,
    PluginImportReport,
)
from src.domains.skills.import_service import (
    _parse_frontmatter_name,
    validate_skill_name,
)
from src.domains.skills.models import Skill
from src.domains.user_mcp.installation import (
    OfflineMCPInstallation,
    ValidatedMCPEndpoint,
)
from src.domains.user_mcp.models import UserMCPServer

if TYPE_CHECKING:
    from src.domains.peers.capability_install import TransferInstallation


def _skill_inventory(installation: TransferInstallation) -> dict[str, str]:
    inventory: dict[str, str] = {}
    for resource in installation.package.files:
        path = Path(resource.path)
        if len(path.parts) != 3 or path.parts[0] != "skills" or path.name != "SKILL.md":
            continue
        name = _parse_frontmatter_name(resource.content.decode("utf-8-sig"))
        validate_skill_name(name)
        if name in inventory.values():
            raise ValueError("Plugin contains duplicate skill identities")
        inventory[path.parent.name] = name
    return inventory


async def install_plugin(
    installation: TransferInstallation,
    db: AsyncSession,
    archive: bytes,
    endpoints: dict[str, ValidatedMCPEndpoint],
) -> None:
    context = await PluginTransferHooks.prepare(installation, db)
    report = await PluginImportService(db).import_upload(
        archive, owner_id=installation.recipient, hooks=context.hooks(endpoints)
    )
    context.record_skips(report)
    await installation.check(db)
    await db.commit()


@dataclass(frozen=True)
class PluginTransferHooks:
    installation: TransferInstallation
    root: PeerCapabilityComponent
    inventory: dict[str, str]
    skills: dict[str, PeerCapabilityComponent]
    servers: dict[str, PeerCapabilityComponent]

    @classmethod
    async def prepare(
        cls, installation: TransferInstallation, db: AsyncSession
    ) -> PluginTransferHooks:
        inventory = _skill_inventory(installation)
        root = await installation.reserve(db, CapabilityKind.PLUGIN, installation.package.name)
        skills = {
            name: await installation.reserve(db, CapabilityKind.SKILL, name)
            for name in inventory.values()
        }
        servers = {
            server.key: await installation.reserve(
                db,
                CapabilityKind.MCP,
                _server_display_name(installation.package.name, server.key),
            )
            for server in installation.package.servers
        }
        await installation.check(db)
        await db.commit()
        return cls(installation, root, inventory, skills, servers)

    async def before_write(self, session: AsyncSession) -> None:
        await self.installation.check(session)
        existing = await session.scalar(
            select(UserPlugin).where(
                UserPlugin.user_id == self.installation.recipient,
                UserPlugin.name == self.installation.package.name,
            )
        )
        if existing is not None and existing.id != self.root.resource_id:
            raise ResourceConflictError("capability", detail="peers_capability_name_conflict")
        if existing is None and self.root.resource_id is not None:
            raise ResourceConflictError("capability", detail="peers_capability_recipient_changed")
        if existing is not None and not self.root.installed:
            manifest_file = next(
                file for file in self.installation.package.files if file.path == "plugin.json"
            )
            manifest = validate_plugin_manifest(json.loads(manifest_file.content)).manifest
            if manifest is None or existing.manifest != manifest.model_dump(
                by_alias=True, exclude_none=True
            ):
                raise ResourceConflictError(
                    "capability", detail="peers_capability_recipient_changed"
                )

    def plugin_written(self, plugin: UserPlugin) -> None:
        self.root.resource_id = plugin.id

    async def before_skill_swap(self, session: AsyncSession, path: Path) -> None:
        await self.installation.check(session)
        name = self.inventory[path.name]
        existing = await session.scalar(
            select(Skill.id).where(
                Skill.name == name,
                or_(
                    Skill.owner_id == self.installation.recipient,
                    Skill.is_system.is_(True),
                ),
            )
        )
        if existing is not None:
            raise ResourceConflictError("capability", detail="peers_capability_name_conflict")

    async def before_server_write(
        self, session: AsyncSession, name: str, existing_id: UUID | None
    ) -> None:
        await self.installation.check(session)
        if existing_id is not None:
            raise ResourceConflictError("capability", detail="peers_capability_name_conflict")

    def server_written(self, server: UserMCPServer) -> None:
        key = next(
            key
            for key in self.servers
            if _server_display_name(self.installation.package.name, key) == server.name
        )
        self.servers[key].resource_id = server.id
        self.servers[key].installed = True
        self.servers[key].error_code = None

    async def root_staged(self, slot: PluginRootSlot) -> None:
        self.root.installed = True

    def record_skips(self, report: PluginImportReport) -> None:
        for result in report.components:
            if result.status is not PluginComponentStatus.SKIPPED:
                continue
            if result.kind is PluginComponentKind.SKILL:
                component = self.skills.get(self.inventory.get(result.key, result.key))
            else:
                component = self.servers.get(result.key)
            if component is not None and not component.installed:
                component.error_code = "peers_capability_component_failed"

    def hooks(self, endpoints: dict[str, ValidatedMCPEndpoint]) -> PluginImportHooks:
        return PluginImportHooks(
            before_write=self.before_write,
            before_commit=self.installation.check,
            before_skill_swap=self.before_skill_swap,
            after_skill_register=self.installation.skill_registered,
            before_server_write=self.before_server_write,
            after_server_write=self.server_written,
            after_plugin_write=self.plugin_written,
            after_root_stage=self.root_staged,
            completed_skills=frozenset(
                name for name, component in self.skills.items() if component.installed
            ),
            completed_servers=frozenset(
                key for key, component in self.servers.items() if component.installed
            ),
            preserve_root=self.root.installed,
            offline_servers={
                server.key: OfflineMCPInstallation(
                    server.config.auth_type,
                    server.config.header_name,
                    endpoints[server.key],
                    server.config.oauth_scopes,
                )
                for server in self.installation.package.servers
            },
        )
