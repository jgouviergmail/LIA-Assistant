"""Per-component CAS fences preserve the original plugin import's partial-commit truth."""

from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.plugin_package_models import (
    PluginImportState,
    PluginPackageCheck,
    PluginPackageWrite,
)
from src.domains.agents.application.plugin_read import require_plugin_access
from src.domains.agents.application.plugin_state import (
    observe_plugin_import_state,
    plugin_root_state,
    row_digest,
    skill_member_state,
)
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.plugins.group_scope import (
    PluginGroup,
    load_plugin_group,
    load_plugin_server_for_write,
)
from src.domains.plugins.import_service import PluginImportService
from src.domains.plugins.models import UserPlugin
from src.domains.plugins.package_preview import PluginPackagePreview
from src.domains.plugins.removal_disk import RemovalMove
from src.domains.plugins.root_commit import PluginRootSlot
from src.domains.plugins.schemas import McpServerStatus, PluginComponentReport
from src.domains.plugins.tree_state import tree_state
from src.domains.skills.import_disk import read_disk_step
from src.domains.skills.lifecycle_lock import lock_skill_owner
from src.domains.skills.models import Skill
from src.domains.skills.repository import SkillRepository
from src.domains.users.preference_cas import PreferenceWriteReceipt

if TYPE_CHECKING:
    from src.domains.user_mcp.models import UserMCPServer


async def require_plugin_package_access(
    db: AsyncSession, owner_id: UUID, package: PluginPackagePreview, state: PluginImportState
) -> None:
    await require_plugin_access(db, owner_id)
    previous = state.previous
    if package.skill_names or previous is not None and previous.skill_names:
        await require_capability_fresh(db, PlatformCapability.SKILLS)
    if (
        any(server.status is McpServerStatus.SUPPORTED for server in package.servers)
        or previous is not None
        and previous.server_names
    ):
        await require_capability_fresh(db, PlatformCapability.MCP)


class PluginImportGuard:
    def __init__(
        self,
        owner_id: UUID,
        draft: ApplicationActionDraftContent,
        write: PluginPackageWrite,
        receipt: PreferenceWriteReceipt,
        check: PluginPackageCheck,
    ) -> None:
        self.owner_id = owner_id
        self.draft = draft
        self.write = write
        self.source_check = check
        self.receipt = receipt
        self.installed: set[str] = set()
        self.server_writes: dict[str, str] = {}
        self.plugin_written_digest: str | None = None
        self.plugin_id: UUID | None = None
        self.remaining_skills: tuple[Skill, ...] = ()
        self.staged_skills: dict[str, Path] = {}
        self.root_slot: PluginRootSlot | None = None

    async def check(self, db: AsyncSession) -> None:
        await self.source_check(db)
        await require_plugin_package_access(db, self.owner_id, self.write.package, self.write.state)
        if datetime.now(UTC) >= self.draft.expires_at:
            raise CommandRejected("EXPIRED")

    async def before_write(self, db: AsyncSession) -> None:
        await self.check(db)
        await lock_skill_owner(db, self.owner_id)
        actual = await observe_plugin_import_state(
            db, self.owner_id, self.write.package.name, self.write.replace_plugin_id
        )
        if actual != self.write.state:
            raise CommandRejected("STALE_STATE")

    async def before_skill_swap(self, db: AsyncSession, path: Path) -> None:
        await self.check(db)
        await lock_skill_owner(db, self.owner_id)
        names = await read_disk_step(lambda: PluginImportService(db)._incoming_skill_names([path]))
        skill = await SkillRepository(db).get_owned(self.owner_id, names[0])
        expected = self.write.state.skills.get(names[0])
        if skill is None:
            if expected is not None:
                raise CommandRejected("STALE_STATE")
            from src.domains.agents.application.skill_import_state import require_absent_skill

            await require_absent_skill(db, self.owner_id, names[0])
        elif (
            expected is None
            or await read_disk_step(lambda: skill_member_state(skill, self.owner_id)) != expected
        ):
            raise CommandRejected("STALE_STATE")

    def skill_committed(self, skill: Skill) -> None:
        self.installed.add(skill.name)
        names: list[JsonValue] = []
        names.extend(sorted(self.installed))
        self.receipt.committed = True
        self.receipt.values = {
            self.write.value_field: {
                "name": self.write.package.name,
                "plugin_id": str(self.plugin_id),
                "complete": False,
                "installed_skill_names": names,
            },
            "cache_refresh_pending": True,
        }

    async def before_drop(self, db: AsyncSession, reports: list[PluginComponentReport]) -> None:
        await self.check(db)
        await lock_skill_owner(db, self.owner_id)
        if (
            await read_disk_step(lambda: plugin_root_state(self.owner_id, self.write.package.name))
            != self.write.state.root_digest
        ):
            raise CommandRejected("STALE_STATE")
        if self.plugin_id is None:
            raise CommandRejected("STALE_STATE")
        group = await load_plugin_group(db, self.owner_id, self.plugin_id, lock=True)
        if row_digest(group.plugin) != self.plugin_written_digest:
            raise CommandRejected("STALE_STATE")
        self.remaining_skills = tuple(
            skill for skill in group.skills if skill.name not in self.installed
        )
        await self._check_remaining_skills(group)
        self._check_servers(group)

    async def _check_remaining_skills(self, group: PluginGroup) -> None:
        for skill in group.skills:
            if skill.name in self.installed:
                continue
            if await read_disk_step(
                partial(skill_member_state, skill, self.owner_id)
            ) != self.write.state.skills.get(skill.name):
                raise CommandRejected("STALE_STATE")

    async def before_server_write(
        self, db: AsyncSession, name: str, server_id: UUID | None
    ) -> None:
        await self.check(db)
        await lock_skill_owner(db, self.owner_id)
        row = await load_plugin_server_for_write(db, self.owner_id, name)
        expected = self.write.state.servers.get(name)
        if server_id is None:
            if row is not None or expected is not None:
                raise CommandRejected("STALE_STATE")
        elif row is None or row.id != server_id or expected is None or row_digest(row) != expected:
            raise CommandRejected("STALE_STATE")

    def server_written(self, server: UserMCPServer) -> None:
        self.server_writes[server.name] = row_digest(server)

    def plugin_written(self, plugin: UserPlugin) -> None:
        self.plugin_written_digest = row_digest(plugin)
        self.plugin_id = plugin.id

    async def after_drop_stage(self, moves: tuple[RemovalMove, ...]) -> None:
        self.staged_skills = {move.source.name: move.destination for move in moves}

    async def after_root_stage(self, slot: PluginRootSlot) -> None:
        self.root_slot = slot

    async def before_commit(self, db: AsyncSession) -> None:
        await self.check(db)
        if self.root_slot is None:
            return
        actual_root = await read_disk_step(
            partial(
                tree_state,
                self.root_slot.previous,
                max_files=settings.plugins_zip_max_files,
                max_bytes=settings.plugins_zip_max_decompressed_kb * 1024,
            )
        )
        if actual_root != self.write.state.root_digest:
            raise CommandRejected("STALE_STATE")
        for skill in self.remaining_skills:
            actual = await read_disk_step(
                partial(
                    skill_member_state,
                    skill,
                    self.owner_id,
                    self.staged_skills.get(skill.name),
                )
            )
            if actual != self.write.state.skills.get(skill.name):
                raise CommandRejected("STALE_STATE")

    def _check_servers(self, group: PluginGroup) -> None:
        for server in group.servers:
            expected = self.server_writes.get(
                server.name, self.write.state.servers.get(server.name)
            )
            if row_digest(server) != expected:
                raise CommandRejected("STALE_STATE")
