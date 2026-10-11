"""External callback stages encrypted tokens; only the original browser may persist them."""

from uuid import UUID

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.personal_mcp_oauth_guard import require_oauth_claim
from src.domains.agents.application.personal_mcp_oauth_schemas import PersonalMCPOAuthPatch
from src.domains.agents.application.personal_mcp_oauth_store import (
    forget_oauth_claim,
    read_oauth_claim,
    stage_oauth_credentials,
)
from src.domains.agents.application.secure_continuation import finish_application_continuation
from src.infrastructure.database.session import get_db_context


async def check_personal_mcp_oauth_callback(
    server_id: UUID, user_id: UUID, command_id: UUID
) -> None:
    ticket = await read_oauth_claim(command_id)
    draft = ticket.command.draft
    selected = PersonalMCPOAuthPatch.model_validate(draft.intent).personal_mcp_oauth
    if user_id != draft.actor_id or server_id != selected.request.server_id:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    async with get_db_context() as db:
        await require_oauth_claim(db, ticket, callback=True)


async def stage_personal_mcp_oauth_callback(
    server_id: UUID, user_id: UUID, command_id: UUID, credentials: str
) -> None:
    await check_personal_mcp_oauth_callback(server_id, user_id, command_id)
    ticket = await read_oauth_claim(command_id)
    await stage_oauth_credentials(ticket, credentials)


async def fail_personal_mcp_oauth_callback(command_id: UUID) -> None:
    ticket = await read_oauth_claim(command_id)
    await finish_application_continuation(
        ticket,
        ApplicationExecutionOutcome(
            success=False,
            phase=ApplicationPhase.FAILED,
            error_code="OAUTH_FAILED",
        ),
    )
    await forget_oauth_claim(command_id)
