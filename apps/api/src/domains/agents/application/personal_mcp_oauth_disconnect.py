"""One original HITL authorizes local token withdrawal without exposing secrets."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ValidationError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_execution import commit_personal_mcp_change
from src.domains.agents.application.personal_mcp_oauth_disconnect_schemas import (
    PersonalMCPOAuthDisconnectInput,
    PersonalMCPOAuthDisconnectObservation,
    PersonalMCPOAuthDisconnectPatch,
    canonical_personal_mcp_oauth_disconnect,
    oauth_disconnect_after,
    oauth_disconnect_before,
)
from src.domains.agents.application.personal_mcp_oauth_disconnect_spec import (
    PERSONAL_MCP_OAUTH_DISCONNECT_OPERATION,
)
from src.domains.agents.application.personal_mcp_read import require_personal_mcp_access
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.mcp.personal_state_contract import PersonalMCPWriteCheck
from src.infrastructure.mcp.personal_state_gateway import get_personal_mcp_state


async def prepare_personal_mcp_oauth_disconnect(
    db: AsyncSession,
    actor_id: UUID,
    request: PersonalMCPOAuthDisconnectInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    desired = PersonalMCPOAuthDisconnectInput.model_validate(request.model_dump())
    await require_personal_mcp_access(db, actor_id)
    gateway = get_personal_mcp_state()
    if gateway.oauth_disconnect is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    expected = await gateway.read(db, actor_id, desired.server_id)
    if expected.server.auth_type != "oauth2":
        raise ValidationError("Only OAuth personal MCP servers can be disconnected")
    await require_personal_mcp_access(db, actor_id)
    if len(expected.model_dump_json().encode("utf-8")) > 64_000:
        raise ValueError("MCP OAuth withdrawal preview too large")
    return build_action_content(
        actor_id,
        PERSONAL_MCP_OAUTH_DISCONNECT_OPERATION,
        PersonalMCPOAuthDisconnectPatch(
            personal_mcp_oauth_disconnect=PersonalMCPOAuthDisconnectObservation(
                request=desired, expected=expected
            )
        ),
        {"personal_mcp_oauth_disconnect": oauth_disconnect_before(expected)},
        {"personal_mcp_oauth_disconnect": oauth_disconnect_after(expected)},
        command_id=command_id,
    )


async def execute_personal_mcp_oauth_disconnect(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if (
        draft.actor_id != actor_id
        or draft.operation_id != PERSONAL_MCP_OAUTH_DISCONNECT_OPERATION.operation_id
    ):
        raise CommandRejected("FORBIDDEN")
    if not canonical_personal_mcp_oauth_disconnect(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = PersonalMCPOAuthDisconnectPatch.model_validate(
        draft.intent
    ).personal_mcp_oauth_disconnect
    writer = get_personal_mcp_state().oauth_disconnect
    if writer is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})

    async def apply(check: PersonalMCPWriteCheck) -> bool:
        return await writer(
            db, actor_id, selected.request.server_id, expected=selected.expected, check=check
        )

    await commit_personal_mcp_change(db, actor_id, draft, receipt, apply)
