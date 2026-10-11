"""Owner-safe settings projection: three queries regardless of plugin count."""

from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.plugins.models import UserPlugin
from src.domains.plugins.schemas import PluginListResponse, PluginResponse
from src.domains.skills.models import Skill
from src.domains.user_mcp.models import UserMCPServer


async def list_plugin_projection(db: AsyncSession, owner_id: UUID) -> PluginListResponse:
    rows = (
        (
            await db.execute(
                select(
                    UserPlugin.id,
                    UserPlugin.name,
                    UserPlugin.version,
                    UserPlugin.description,
                    UserPlugin.spec_version,
                    UserPlugin.created_at,
                    UserPlugin.updated_at,
                )
                .where(UserPlugin.user_id == owner_id)
                .order_by(UserPlugin.name, UserPlugin.id)
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        return PluginListResponse()
    ids = [row["id"] for row in rows]
    skills: dict[UUID, list[str]] = defaultdict(list)
    for plugin_id, name in (
        await db.execute(
            select(Skill.plugin_id, Skill.name)
            .where(Skill.owner_id == owner_id, Skill.plugin_id.in_(ids))
            .order_by(Skill.name, Skill.id)
        )
    ).all():
        skills[plugin_id].append(name)
    servers: dict[UUID, list[str]] = defaultdict(list)
    for plugin_id, name in (
        await db.execute(
            select(UserMCPServer.plugin_id, UserMCPServer.name)
            .where(UserMCPServer.user_id == owner_id, UserMCPServer.plugin_id.in_(ids))
            .order_by(UserMCPServer.name, UserMCPServer.id)
        )
    ).all():
        servers[plugin_id].append(name)
    items = [
        PluginResponse(**row, skill_names=skills[row["id"]], server_names=servers[row["id"]])
        for row in rows
    ]
    return PluginListResponse(plugins=items, total=len(items))
