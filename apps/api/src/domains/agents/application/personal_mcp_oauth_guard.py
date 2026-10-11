"""Fresh nonlocking callback checks and exact browser checks share the approved claim."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_origin_binding import (
    require_command_origin,
    require_command_origin_alive,
)
from src.domains.agents.application.command_repository import get_command
from src.domains.agents.application.continuation_approval import ApprovedInteractionClaim
from src.domains.agents.application.continuation_settlement import matching_continuation_records
from src.domains.agents.application.personal_mcp_execution import check_personal_mcp_write
from src.domains.agents.application.personal_mcp_oauth_schemas import (
    PersonalMCPOAuthPatch,
    canonical_personal_mcp_oauth,
)
from src.infrastructure.mcp.personal_state_gateway import get_personal_mcp_state


async def require_oauth_claim(
    db: AsyncSession,
    ticket: ApprovedInteractionClaim,
    *,
    origin: ApplicationOrigin | None = None,
    callback: bool = False,
    lock: bool = False,
    compare_snapshot: bool = True,
) -> None:
    draft = ticket.command.draft
    if draft.operation_id != "personal_mcp.oauth_authorize" or not canonical_personal_mcp_oauth(
        draft
    ):
        raise AuthorizationError(detail={"error_code": "INVALID_DRAFT"})
    await check_personal_mcp_write(db, draft.actor_id, draft)
    if not await matching_continuation_records(db, ticket, lock=lock):
        raise AuthorizationError(detail={"error_code": "INVALID_APPROVAL"})
    command = await get_command(db, draft.command_id, draft.actor_id)
    if command is None:
        raise AuthorizationError(detail={"error_code": "INVALID_APPROVAL"})
    if callback:
        await require_command_origin_alive(command)
    else:
        await require_command_origin(command, origin)
    selected = PersonalMCPOAuthPatch.model_validate(draft.intent).personal_mcp_oauth
    if compare_snapshot:
        actual = await get_personal_mcp_state().read(db, draft.actor_id, selected.request.server_id)
        if actual != selected.expected:
            raise ResourceConflictError("user_mcp_server", detail={"error_code": "STALE_STATE"})
    await check_personal_mcp_write(db, draft.actor_id, draft)
