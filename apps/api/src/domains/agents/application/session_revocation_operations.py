"""Read-only preparation of an exact, original-session-bound revocation."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.preparation import _preference_content
from src.domains.agents.application.session_revocation_schemas import (
    DeviceSessionRevokePatch,
    DeviceSessionRevokeRequest,
)
from src.domains.auth.session_commands import read_owned_session_for_revocation


async def prepare_session_revocation(
    db: AsyncSession,
    actor_id: UUID,
    request: DeviceSessionRevokeRequest,
    *,
    origin: ApplicationOrigin | None,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    validated = DeviceSessionRevokeRequest.model_validate(request)
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    selected = await read_owned_session_for_revocation(db, actor, origin, validated.display_id)
    await require_application_tools(db)
    await load_actor(db, actor_id)
    patch = DeviceSessionRevokePatch(session_to_revoke=selected)
    return _preference_content(
        actor_id, patch, patch.model_dump(mode="json"), command_id=command_id
    )
