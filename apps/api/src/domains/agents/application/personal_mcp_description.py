"""Provider spend precedes locks; exact current authority/CAS guards the later write."""

from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ValidationError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_description_schemas import (
    PersonalMCPDescriptionInput,
    PersonalMCPDescriptionObservation,
    PersonalMCPDescriptionPatch,
    canonical_personal_mcp_description,
    description_after,
    description_before,
)
from src.domains.agents.application.personal_mcp_description_spec import (
    PERSONAL_MCP_DESCRIPTION_OPERATION,
)
from src.domains.agents.application.personal_mcp_execution import (
    check_personal_mcp_write,
    commit_personal_mcp_change,
    lock_personal_mcp_write,
)
from src.domains.agents.application.personal_mcp_read import require_personal_mcp_access
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.mcp.personal_state_contract import PersonalMCPWriteCheck
from src.infrastructure.mcp.personal_state_gateway import get_personal_mcp_state


async def prepare_personal_mcp_description(
    db: AsyncSession,
    actor_id: UUID,
    request: PersonalMCPDescriptionInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    desired = PersonalMCPDescriptionInput.model_validate(request.model_dump())
    await require_personal_mcp_access(db, actor_id)
    gateway = get_personal_mcp_state()
    if gateway.describe is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    expected = await gateway.read(db, actor_id, desired.server_id)
    if not expected.server.tool_count:
        raise ValidationError("No cached tools available; test the connection first")
    await require_personal_mcp_access(db, actor_id)
    if len(expected.model_dump_json().encode("utf-8")) > 64_000:
        raise ValueError("MCP generation preview too large")
    return build_action_content(
        actor_id,
        PERSONAL_MCP_DESCRIPTION_OPERATION,
        PersonalMCPDescriptionPatch(
            personal_mcp_description=PersonalMCPDescriptionObservation(
                request=desired, expected=expected
            )
        ),
        {"personal_mcp_description": description_before(expected)},
        {"personal_mcp_description": description_after(expected)},
        command_id=command_id,
    )


async def execute_personal_mcp_description(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if (
        draft.actor_id != actor_id
        or draft.operation_id != PERSONAL_MCP_DESCRIPTION_OPERATION.operation_id
    ):
        raise CommandRejected("FORBIDDEN")
    if not canonical_personal_mcp_description(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = PersonalMCPDescriptionPatch.model_validate(draft.intent).personal_mcp_description
    writer = get_personal_mcp_state().describe
    if writer is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})

    async def read_check(session: AsyncSession) -> None:
        await check_personal_mcp_write(session, actor_id, draft)

    async def write_check(session: AsyncSession) -> None:
        await lock_personal_mcp_write(session, actor_id, draft)

    result = await writer(
        db,
        actor_id,
        selected.request.server_id,
        expected=selected.expected,
        read_check=read_check,
        write_check=write_check,
    )

    async def saved(check: PersonalMCPWriteCheck) -> bool:
        await check(db)
        return True

    observed_values: dict[str, JsonValue] = {
        "personal_mcp_description": {
            "server_id": str(selected.request.server_id),
            **result.model_dump(mode="json"),
        }
    }
    await commit_personal_mcp_change(
        db, actor_id, draft, receipt, saved, committed_values=observed_values
    )
