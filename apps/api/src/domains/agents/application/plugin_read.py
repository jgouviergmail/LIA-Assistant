"""Plugin metadata uses the original settings port and fresh application authority."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.plugin_read_schemas import (
    PluginReadInput,
    PluginReadItem,
    PluginReadProjection,
)
from src.domains.plugins.projection import list_plugin_projection


async def require_plugin_access(db: AsyncSession, owner_id: UUID) -> None:
    await require_application_tools(db)
    await load_actor(db, owner_id)
    if not settings.plugins_enabled:
        raise AuthorizationError(detail={"error_code": "CAPABILITY_DISABLED"})


async def read_plugins(
    db: AsyncSession, owner_id: UUID, query: PluginReadInput
) -> PluginReadProjection:
    selected = PluginReadInput.model_validate(query.model_dump())
    await require_plugin_access(db, owner_id)
    data = await list_plugin_projection(db, owner_id)
    items = tuple(
        PluginReadItem.model_validate(row.model_dump(exclude={"shared_origin", "shared_with"}))
        for row in data.plugins[selected.offset : selected.offset + selected.limit]
    )
    await require_plugin_access(db, owner_id)
    end = selected.offset + len(items)
    result = PluginReadProjection(
        observed_at=datetime.now(UTC),
        items=items,
        total=data.total,
        next_offset=end if end < data.total else None,
    )
    if len(result.model_dump_json().encode("utf-8")) > 64_000:
        raise ValueError("Plugin metadata projection too large; request a smaller page")
    return result
