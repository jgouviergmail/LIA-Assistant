"""Confirmed standalone deletion shares the original CAS and exact commit boundary."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ValidationError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_delete_schemas import (
    PersonalMCPDeleteInput,
    PersonalMCPDeleteObservation,
    PersonalMCPDeletePatch,
    canonical_personal_mcp_delete,
)
from src.domains.agents.application.personal_mcp_delete_spec import PERSONAL_MCP_DELETE_OPERATION
from src.domains.agents.application.personal_mcp_execution import commit_personal_mcp_change
from src.domains.agents.application.personal_mcp_read import require_personal_mcp_access
from src.domains.agents.application.personal_mcp_state_schemas import personal_mcp_state_target
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.mcp.personal_state_contract import PersonalMCPWriteCheck
from src.infrastructure.mcp.personal_state_gateway import get_personal_mcp_state


async def prepare_personal_mcp_delete(
    db: AsyncSession,
    actor_id: UUID,
    request: PersonalMCPDeleteInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    desired = PersonalMCPDeleteInput.model_validate(request.model_dump())
    await require_personal_mcp_access(db, actor_id)
    gateway = get_personal_mcp_state()
    if gateway.remove is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    expected = await gateway.read(db, actor_id, desired.server_id)
    if expected.server.plugin_id is not None:
        raise ValidationError("Plugin-installed servers require complete plugin uninstall")
    await require_personal_mcp_access(db, actor_id)
    if len(expected.model_dump_json().encode("utf-8")) > 64_000:
        raise ValueError("MCP deletion preview too large")
    return build_action_content(
        actor_id,
        PERSONAL_MCP_DELETE_OPERATION,
        PersonalMCPDeletePatch(
            personal_mcp_server_delete=PersonalMCPDeleteObservation(
                request=desired, expected=expected
            )
        ),
        {"personal_mcp_server_delete": personal_mcp_state_target(expected)},
        {"personal_mcp_server_delete": None},
        command_id=command_id,
    )


async def execute_personal_mcp_delete(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if (
        draft.actor_id != actor_id
        or draft.operation_id != PERSONAL_MCP_DELETE_OPERATION.operation_id
    ):
        raise CommandRejected("FORBIDDEN")
    if not canonical_personal_mcp_delete(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = PersonalMCPDeletePatch.model_validate(draft.intent).personal_mcp_server_delete
    writer = get_personal_mcp_state().remove
    if writer is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})

    async def apply(check: PersonalMCPWriteCheck) -> bool:
        return await writer(
            db, actor_id, selected.request.server_id, expected=selected.expected, check=check
        )

    await commit_personal_mcp_change(db, actor_id, draft, receipt, apply)
