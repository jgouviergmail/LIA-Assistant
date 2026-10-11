"""An exact original browser selects and submits private configuration outside chat."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_configuration_schemas import (
    PersonalMCPConfigurationInput,
    PersonalMCPConfigurationObservation,
    PersonalMCPConfigurationPatch,
    configuration_after,
    configuration_before,
)
from src.domains.agents.application.personal_mcp_configuration_spec import (
    PERSONAL_MCP_CONFIGURATION_OPERATION,
)
from src.domains.agents.application.personal_mcp_read import require_personal_mcp_access
from src.infrastructure.mcp.personal_state_gateway import get_personal_mcp_state


async def authorize_personal_mcp_configuration(
    db: AsyncSession, actor_id: UUID, origin: ApplicationOrigin | None
) -> None:
    await require_personal_mcp_access(db, actor_id)
    if origin is None:
        raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
    await origin.require_session(actor_id, expected_binding=origin.binding_id)
    await require_personal_mcp_access(db, actor_id)


async def prepare_personal_mcp_configuration(
    db: AsyncSession,
    actor_id: UUID,
    request: PersonalMCPConfigurationInput,
    *,
    origin: ApplicationOrigin | None,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    desired = PersonalMCPConfigurationInput.model_validate(request.model_dump())
    await authorize_personal_mcp_configuration(db, actor_id, origin)
    gateway = get_personal_mcp_state()
    if gateway.configure is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    expected = await gateway.read(db, actor_id, desired.server_id) if desired.server_id else None
    selected = PersonalMCPConfigurationObservation(request=desired, expected=expected)
    if len(selected.model_dump_json().encode("utf-8")) > 64_000:
        raise ValueError("MCP configuration preview too large")
    await authorize_personal_mcp_configuration(db, actor_id, origin)
    return build_action_content(
        actor_id,
        PERSONAL_MCP_CONFIGURATION_OPERATION,
        PersonalMCPConfigurationPatch(personal_mcp_configuration=selected),
        {"personal_mcp_configuration": configuration_before(selected)},
        {"personal_mcp_configuration": configuration_after(selected)},
        command_id=command_id,
    )
