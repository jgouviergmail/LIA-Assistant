"""Preparation observes an owned row without discovery, registration or credentials."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_configuration import (
    authorize_personal_mcp_configuration,
)
from src.domains.agents.application.personal_mcp_oauth_schemas import (
    PersonalMCPOAuthInput,
    PersonalMCPOAuthObservation,
    PersonalMCPOAuthPatch,
    oauth_after,
    oauth_before,
)
from src.domains.agents.application.personal_mcp_oauth_spec import PERSONAL_MCP_OAUTH_OPERATION
from src.infrastructure.mcp.personal_state_gateway import get_personal_mcp_state


async def prepare_personal_mcp_oauth(
    db: AsyncSession,
    actor_id: UUID,
    request: PersonalMCPOAuthInput,
    *,
    origin: ApplicationOrigin | None,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    desired = PersonalMCPOAuthInput.model_validate(request.model_dump())
    await authorize_personal_mcp_configuration(db, actor_id, origin)
    gateway = get_personal_mcp_state()
    if (
        gateway.oauth_start is None
        or gateway.oauth_save is None
        or not settings.mcp_user_oauth_callback_base_url
    ):
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    expected = await gateway.read(db, actor_id, desired.server_id)
    if expected.server.auth_type != "oauth2":
        raise ValueError("Select an OAuth personal MCP server")
    selected = PersonalMCPOAuthObservation(request=desired, expected=expected)
    await authorize_personal_mcp_configuration(db, actor_id, origin)
    return build_action_content(
        actor_id,
        PERSONAL_MCP_OAUTH_OPERATION,
        PersonalMCPOAuthPatch(personal_mcp_oauth=selected),
        {"personal_mcp_oauth": oauth_before(expected)},
        {"personal_mcp_oauth": oauth_after(expected)},
        command_id=command_id,
    )
