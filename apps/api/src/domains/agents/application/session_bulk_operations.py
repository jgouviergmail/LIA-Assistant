"""Preparation freezes the fleet; the approved execution first requests secure interaction."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.auth.session_bulk_commands import read_owned_other_device_sessions
from src.domains.auth.session_bulk_schemas import OtherDeviceSessionsSelection


class OtherSessionsRevokePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    other_sessions_to_revoke: OtherDeviceSessionsSelection


SESSION_FLEET_OPERATION = ApplicationOperationSpec(
    operation_id="device_sessions.revoke_others",
    tool_name="revoke_lia_other_device_sessions_tool",
    sections=("security-devices",),
    input_model=OtherSessionsRevokePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.SECURE_HANDOFF,
)


async def prepare_other_sessions_revocation(
    db: AsyncSession,
    actor_id: UUID,
    *,
    origin: ApplicationOrigin | None,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    selection = await read_owned_other_device_sessions(db, actor, origin)
    await require_application_tools(db)
    await load_actor(db, actor_id)
    patch = OtherSessionsRevokePatch(other_sessions_to_revoke=selection)
    return build_action_content(
        actor_id,
        SESSION_FLEET_OPERATION,
        patch,
        patch.model_dump(mode="json"),
        {"other_sessions_to_revoke": None},
        command_id=command_id,
    )
