"""Shared complete plugin group and member witnesses keep private data in local hashes."""

from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.plugin_package_models import PluginImportState
from src.domains.agents.application.plugin_read_schemas import PluginReadItem
from src.domains.agents.effects.digest import payload_digest
from src.domains.plugins.group_scope import PluginGroup, load_plugin_group
from src.domains.plugins.removal_disk import RemovalMove, group_paths
from src.domains.plugins.repository import UserPluginRepository
from src.domains.plugins.tree_state import tree_state
from src.domains.skills.import_disk import read_disk_step

if TYPE_CHECKING:
    from src.domains.plugins.models import UserPlugin
    from src.domains.skills.models import Skill
    from src.domains.user_mcp.models import UserMCPServer


def row_digest(row: UserPlugin | Skill | UserMCPServer) -> str:
    return payload_digest(
        {column.key: getattr(row, column.key) for column in row.__table__.columns}
    )


def plugin_public_item(group: PluginGroup) -> PluginReadItem:
    row = group.plugin
    return PluginReadItem(
        id=row.id,
        name=row.name,
        version=row.version,
        description=row.description,
        spec_version=row.spec_version,
        skill_names=sorted(skill.name for skill in group.skills),
        server_names=sorted(server.name for server in group.servers),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def plugin_root_state(owner_id: UUID, name: str) -> str:
    return tree_state(
        Path(settings.plugins_users_path) / str(owner_id) / name,
        max_files=settings.plugins_zip_max_files,
        max_bytes=settings.plugins_zip_max_decompressed_kb * 1024,
    )


def skill_member_state(skill: Skill, owner_id: UUID, root: Path | None = None) -> str:
    files = tree_state(
        root if root is not None else Path(settings.skills_users_path) / str(owner_id) / skill.name,
        max_files=settings.skills_zip_max_files,
        max_bytes=settings.skills_zip_max_decompressed_kb * 1024,
    )
    return payload_digest({"row": row_digest(skill), "files": files})


def plugin_group_witness(
    group: PluginGroup, owner_id: UUID, staged: tuple[RemovalMove, ...] = ()
) -> str:
    group_paths(group, owner_id)
    replacements = {move.source: move.destination for move in staged}

    def located(base: str, name: str) -> Path:
        source = (Path(base) / str(owner_id) / name).absolute()
        return replacements.get(source, source)

    rows = [row_digest(row) for row in (group.plugin, *group.skills, *group.servers)]
    files = {
        "plugin": tree_state(
            located(settings.plugins_users_path, group.plugin.name),
            max_files=settings.plugins_zip_max_files,
            max_bytes=settings.plugins_zip_max_decompressed_kb * 1024,
        )
    }
    for skill in group.skills:
        files[str(skill.id)] = tree_state(
            located(settings.skills_users_path, skill.name),
            max_files=settings.skills_zip_max_files,
            max_bytes=settings.skills_zip_max_decompressed_kb * 1024,
        )
    return payload_digest({"rows": rows, "files": files})


async def observe_plugin_import_state(
    db: AsyncSession, owner_id: UUID, name: str, replace_id: UUID | None
) -> PluginImportState:
    existing = await UserPluginRepository(db).get_by_name_for_user(owner_id, name)
    if replace_id is None:
        root = Path(settings.plugins_users_path) / str(owner_id) / name
        if existing is not None or root.exists() or root.is_symlink() or root.is_junction():
            raise CommandRejected("STALE_STATE")
        absent = payload_digest({"absent": name})
        return PluginImportState(
            previous=None,
            digest=absent,
            root_digest=await read_disk_step(lambda: plugin_root_state(owner_id, name)),
            skills={},
            servers={},
        )
    if existing is None or existing.id != replace_id:
        raise CommandRejected("INVALID_INPUT")
    group = await load_plugin_group(db, owner_id, replace_id)

    def observe() -> PluginImportState:
        return PluginImportState(
            previous=plugin_public_item(group),
            digest=plugin_group_witness(group, owner_id),
            root_digest=plugin_root_state(owner_id, name),
            skills={skill.name: skill_member_state(skill, owner_id) for skill in group.skills},
            servers={server.name: row_digest(server) for server in group.servers},
        )

    return await read_disk_step(observe)
