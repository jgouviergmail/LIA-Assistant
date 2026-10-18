"""Optional native authority fences preserve the original per-component commit model."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.plugins.models import UserPlugin
from src.domains.plugins.removal_disk import RemovalMove
from src.domains.plugins.root_commit import PluginRootSlot
from src.domains.plugins.schemas import PluginComponentReport
from src.domains.skills.import_hooks import AfterSkillCommit, BeforeSkillSwap
from src.domains.skills.models import Skill
from src.domains.user_mcp.installation import OfflineMCPInstallation

if TYPE_CHECKING:
    from src.domains.user_mcp.models import UserMCPServer


@dataclass(frozen=True)
class PluginImportHooks:
    completed_skills: frozenset[str] = frozenset()
    completed_servers: frozenset[str] = frozenset()
    preserve_root: bool = False
    offline_servers: dict[str, OfflineMCPInstallation] | None = None
    after_skill_register: Callable[[AsyncSession, Skill], Awaitable[None]] | None = None
    before_write: Callable[[AsyncSession], Awaitable[None]] | None = None
    before_skill_swap: Callable[[AsyncSession, Path], Awaitable[None]] | None = None
    before_drop: Callable[[AsyncSession, list[PluginComponentReport]], Awaitable[None]] | None = (
        None
    )
    before_commit: BeforeSkillSwap | None = None
    before_server_write: Callable[[AsyncSession, str, UUID | None], Awaitable[None]] | None = None
    after_server_write: Callable[[UserMCPServer], None] | None = None
    after_plugin_write: Callable[[UserPlugin], None] | None = None
    after_drop_stage: Callable[[tuple[RemovalMove, ...]], Awaitable[None]] | None = None
    after_root_stage: Callable[[PluginRootSlot], Awaitable[None]] | None = None
    after_skill_commit: AfterSkillCommit | None = None
    after_root_commit: Callable[[UserPlugin], None] | None = None

    async def check_commit(self, db: AsyncSession) -> None:
        if self.before_commit is not None:
            await self.before_commit(db)

    def root_committed(self, plugin: UserPlugin) -> None:
        if self.after_root_commit is not None:
            self.after_root_commit(plugin)

    async def check_skill_swap(self, path: Path, db: AsyncSession) -> None:
        if self.before_skill_swap is not None:
            await self.before_skill_swap(db, path)

    async def check_server_write(self, name: str, server_id: UUID | None, db: AsyncSession) -> None:
        if self.before_server_write is not None:
            await self.before_server_write(db, name, server_id)

    def server_written(self, server: UserMCPServer) -> None:
        if self.after_server_write is not None:
            self.after_server_write(server)

    def plugin_written(self, plugin: UserPlugin) -> None:
        if self.after_plugin_write is not None:
            self.after_plugin_write(plugin)

    def pending_components(
        self, skill_names: list[str], server_names: set[str], plugin_name: str
    ) -> tuple[list[str], set[str]]:
        return (
            [name for name in skill_names if name not in self.completed_skills],
            server_names - {f"{plugin_name}:{key}" for key in self.completed_servers},
        )
