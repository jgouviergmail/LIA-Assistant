"""A plugin's complete group is validated before any member can be removed."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.plugins.exceptions import raise_plugin_not_found
from src.domains.plugins.models import UserPlugin
from src.domains.skills.lifecycle_lock import lock_skill_owner
from src.domains.skills.models import Skill, UserSkillState
from src.domains.user_mcp.models import UserMCPServer


@dataclass(frozen=True)
class PluginGroup:
    plugin: UserPlugin
    skills: tuple[Skill, ...]
    servers: tuple[UserMCPServer, ...]


async def load_plugin_server_for_write(
    db: AsyncSession, owner_id: UUID, name: str
) -> UserMCPServer | None:
    """A package endpoint CAS reads the complete current row under its own lock."""
    server: UserMCPServer | None = await db.scalar(
        select(UserMCPServer)
        .where(UserMCPServer.user_id == owner_id, UserMCPServer.name == name)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return server


async def load_plugin_group(
    db: AsyncSession, owner_id: UUID, plugin_id: UUID, *, lock: bool = False
) -> PluginGroup:
    if lock:
        await lock_skill_owner(db, owner_id)
    plugin_query = (
        select(UserPlugin)
        .where(UserPlugin.id == plugin_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        plugin_query = plugin_query.with_for_update()
    plugin = await db.scalar(plugin_query)
    if plugin is None or plugin.user_id != owner_id:
        raise_plugin_not_found(str(plugin_id))
    skill_query = (
        select(Skill)
        .where(Skill.plugin_id == plugin_id)
        .order_by(Skill.id)
        .execution_options(populate_existing=True)
    )
    server_query = (
        select(UserMCPServer)
        .where(UserMCPServer.plugin_id == plugin_id)
        .order_by(UserMCPServer.id)
        .execution_options(populate_existing=True)
    )
    if lock:
        skill_query = skill_query.with_for_update()
        server_query = server_query.with_for_update()
    skills = tuple((await db.scalars(skill_query)).all())
    servers = tuple((await db.scalars(server_query)).all())
    if any(skill.owner_id != owner_id or skill.is_system for skill in skills):
        raise ValueError("Plugin skill scope inconsistent")
    if any(server.user_id != owner_id for server in servers):
        raise ValueError("Plugin server scope inconsistent")
    if skills:
        foreign = await db.scalar(
            select(UserSkillState.id)
            .where(
                UserSkillState.skill_id.in_([row.id for row in skills]),
                UserSkillState.user_id != owner_id,
            )
            .limit(1)
        )
        if foreign is not None:
            raise ValueError("Plugin skill state scope inconsistent")
    return PluginGroup(plugin, skills, servers)
