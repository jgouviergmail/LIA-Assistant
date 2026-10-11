"""Native non-secret edits reuse the original owner and shared confirmed commit boundary."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_execution import commit_personal_mcp_change
from src.domains.agents.application.personal_mcp_read import require_personal_mcp_access
from src.domains.agents.application.personal_mcp_settings_schemas import (
    PersonalMCPSettingsInput,
    PersonalMCPSettingsObservation,
    PersonalMCPSettingsPatch,
    canonical_personal_mcp_settings,
    personal_mcp_settings_target,
)
from src.domains.agents.application.personal_mcp_settings_spec import (
    PERSONAL_MCP_SETTINGS_OPERATION,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.mcp.personal_state_contract import PersonalMCPWriteCheck
from src.infrastructure.mcp.personal_state_gateway import get_personal_mcp_state


async def prepare_personal_mcp_settings(
    db: AsyncSession,
    actor_id: UUID,
    request: PersonalMCPSettingsInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    desired = PersonalMCPSettingsInput.model_validate(request.model_dump(exclude_unset=True))
    await require_personal_mcp_access(db, actor_id)
    gateway = get_personal_mcp_state()
    if gateway.settings is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    expected = await gateway.read(db, actor_id, desired.server_id)
    await require_personal_mcp_access(db, actor_id)
    if len(expected.model_dump_json().encode("utf-8")) > 64_000:
        raise ValueError("MCP settings preview too large")
    return build_action_content(
        actor_id,
        PERSONAL_MCP_SETTINGS_OPERATION,
        PersonalMCPSettingsPatch(
            personal_mcp_settings=PersonalMCPSettingsObservation(request=desired, expected=expected)
        ),
        {"personal_mcp_settings": personal_mcp_settings_target(expected)},
        {"personal_mcp_settings": personal_mcp_settings_target(expected, desired.patch)},
        command_id=command_id,
    )


async def execute_personal_mcp_settings(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if (
        draft.actor_id != actor_id
        or draft.operation_id != PERSONAL_MCP_SETTINGS_OPERATION.operation_id
    ):
        raise CommandRejected("FORBIDDEN")
    if not canonical_personal_mcp_settings(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = PersonalMCPSettingsPatch.model_validate(draft.intent).personal_mcp_settings
    writer = get_personal_mcp_state().settings
    if writer is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})

    async def apply(check: PersonalMCPWriteCheck) -> bool:
        return await writer(
            db,
            actor_id,
            selected.request.server_id,
            selected.request.patch,
            expected=selected.expected,
            check=check,
        )

    await commit_personal_mcp_change(db, actor_id, draft, receipt, apply)
