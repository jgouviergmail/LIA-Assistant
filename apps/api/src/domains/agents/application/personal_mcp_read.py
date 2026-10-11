"""Personal MCP metadata uses the original projection and fresh account capability."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.personal_mcp_read_schemas import (
    PersonalMCPReadInput,
    PersonalMCPReadProjection,
)
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.infrastructure.mcp.personal_metadata_gateway import get_personal_mcp_metadata


async def require_personal_mcp_access(db: AsyncSession, owner_id: UUID) -> None:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.MCP)
    await load_actor(db, owner_id)
    if not settings.mcp_user_enabled:
        raise AuthorizationError(detail={"error_code": "CAPABILITY_DISABLED"})


async def read_personal_mcp(
    db: AsyncSession, owner_id: UUID, query: PersonalMCPReadInput
) -> PersonalMCPReadProjection:
    selected = PersonalMCPReadInput.model_validate(query.model_dump())
    await require_personal_mcp_access(db, owner_id)
    items, total = await get_personal_mcp_metadata()(
        db,
        owner_id,
        server_id=selected.server_id,
        offset=selected.offset,
        limit=selected.limit,
        tools_offset=selected.tools_offset,
        tools_limit=selected.tools_limit,
    )
    await require_personal_mcp_access(db, owner_id)
    end = selected.offset + len(items)
    result = PersonalMCPReadProjection(
        observed_at=datetime.now(UTC),
        items=items,
        total=total,
        next_offset=end if end < total else None,
    )
    if len(result.model_dump_json().encode("utf-8")) > 64_000:
        raise ValueError("MCP metadata projection too large; request a smaller server/tool page")
    return result
