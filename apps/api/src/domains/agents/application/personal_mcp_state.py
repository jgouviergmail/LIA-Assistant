"""One confirmed explicit personal MCP state uses current authority and original CAS."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_execution import commit_personal_mcp_change
from src.domains.agents.application.personal_mcp_read import require_personal_mcp_access
from src.domains.agents.application.personal_mcp_state_schemas import (
    PersonalMCPStateInput,
    PersonalMCPStateObservation,
    PersonalMCPStatePatch,
    canonical_personal_mcp_state,
    personal_mcp_state_target,
)
from src.domains.agents.application.personal_mcp_state_spec import PERSONAL_MCP_STATE_OPERATION
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.mcp.personal_state_contract import PersonalMCPWriteCheck
from src.infrastructure.mcp.personal_state_gateway import get_personal_mcp_state


async def prepare_personal_mcp_state(
    db: AsyncSession,
    actor_id: UUID,
    request: PersonalMCPStateInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    desired = PersonalMCPStateInput.model_validate(request.model_dump())
    await require_personal_mcp_access(db, actor_id)
    expected = await get_personal_mcp_state().read(db, actor_id, desired.server_id)
    await require_personal_mcp_access(db, actor_id)
    if len(expected.model_dump_json().encode("utf-8")) > 64_000:
        raise ValueError("MCP state preview too large")
    return build_action_content(
        actor_id,
        PERSONAL_MCP_STATE_OPERATION,
        PersonalMCPStatePatch(
            personal_mcp_state=PersonalMCPStateObservation(request=desired, expected=expected)
        ),
        {"personal_mcp_state": personal_mcp_state_target(expected)},
        {"personal_mcp_state": personal_mcp_state_target(expected, desired.enabled)},
        command_id=command_id,
    )


async def execute_personal_mcp_state(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if (
        draft.actor_id != actor_id
        or draft.operation_id != PERSONAL_MCP_STATE_OPERATION.operation_id
    ):
        raise CommandRejected("FORBIDDEN")
    if not canonical_personal_mcp_state(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = PersonalMCPStatePatch.model_validate(draft.intent).personal_mcp_state

    async def apply(check: PersonalMCPWriteCheck) -> bool:
        return await get_personal_mcp_state().write(
            db,
            actor_id,
            selected.request.server_id,
            selected.request.enabled,
            expected=selected.expected,
            check=check,
        )

    await commit_personal_mcp_change(db, actor_id, draft, receipt, apply)
