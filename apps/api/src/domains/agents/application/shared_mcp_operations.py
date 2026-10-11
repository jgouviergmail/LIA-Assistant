"""Effect-free shared MCP preferences use the injected domain owner and current authority."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.preparation import _preference_content
from src.domains.agents.application.shared_mcp_schemas import (
    SharedMCPPreferencePatch,
    SharedMCPPreferenceProjection,
    SharedMCPPreferenceRead,
    SharedMCPPreferenceUpdateRequest,
    SharedMCPPreferenceValue,
)
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.infrastructure.mcp.preferences_contract import SharedMCPPreferenceSnapshot
from src.infrastructure.mcp.preferences_gateway import get_shared_mcp_preferences


async def _read_current_shared(
    db: AsyncSession,
    actor_id: UUID,
    server_key: str | None,
) -> list[SharedMCPPreferenceSnapshot]:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.MCP)
    await load_actor(db, actor_id)
    return await get_shared_mcp_preferences().read(db, actor_id, server_key)


async def read_shared_mcp_preferences(
    db: AsyncSession, actor_id: UUID, request: SharedMCPPreferenceRead
) -> SharedMCPPreferenceProjection:
    values = await _read_current_shared(db, actor_id, request.server_key)
    ordered = sorted(values, key=lambda value: value.server_key)
    remaining = [
        value
        for value in ordered
        if request.after_key is None or value.server_key > request.after_key
    ]
    page = remaining[: request.limit]
    return SharedMCPPreferenceProjection(
        servers=[
            SharedMCPPreferenceValue(
                server_key=value.server_key,
                name=value.name,
                enabled_for_user=value.enabled_for_user,
                tools_count=value.tools_count,
            )
            for value in page
        ],
        total=len(values),
        next_cursor=page[-1].server_key if len(remaining) > request.limit else None,
    )


async def prepare_shared_mcp_content(
    db: AsyncSession,
    actor_id: UUID,
    request: SharedMCPPreferenceUpdateRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    values = await _read_current_shared(db, actor_id, request.server_key)
    if len(values) != 1 or values[0].server_key != request.server_key:
        raise ResourceNotFoundError("shared_mcp_server", request.server_key)
    before = values[0]
    return _preference_content(
        actor_id,
        SharedMCPPreferencePatch(
            shared_mcp_server=before.model_copy(update={"enabled_for_user": request.enabled})
        ),
        {"shared_mcp_server": before.model_dump(mode="json")},
        command_id=command_id,
    )
