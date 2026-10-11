"""The native recorder tool proposes; the original browser owner alone captures."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.application.recording_device import (
    prepare_recording_device,
    read_recording_device,
)
from src.domains.agents.application.recording_device_schemas import RecordingDeviceRequest
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


@write_tool(name="control_lia_meeting_recording", agent_name="setting_agent")
async def control_lia_meeting_recording_tool(
    request: RecordingDeviceRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Propose a finite original recorder action on this browser after human confirmation.

    Args:
        request: Start, stop, resume, finalize with gaps or discard.
        runtime: Injected authenticated transport and observed device context.

    Returns:
        An original application HITL proposal, never completed capture or minutes.
    """

    async def prepare(
        db: AsyncSession, actor_id: UUID, selected: RecordingDeviceRequest
    ) -> ApplicationActionDraftContent:
        return await prepare_recording_device(
            db,
            actor_id,
            selected,
            runtime.context.application_origin if runtime is not None else None,
        )

    return await prepare_native_tool(
        request,
        runtime,
        name="control_lia_meeting_recording_tool",
        model=RecordingDeviceRequest,
        prepare=prepare,
        sessions=get_db_context,
    )


@read_tool(name="get_lia_meeting_recorder", agent_name="setting_agent")
async def get_lia_meeting_recorder_tool(
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read the originating browser's explicitly device-reported recorder observation.

    Args:
        runtime: Injected authenticated transport and observed device context.

    Returns:
        Phase, support and original meeting id; no action, secrets or server proof.
    """
    actor = validate_runtime_config(runtime, "get_lia_meeting_recorder_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        async with get_db_context() as db:
            snapshot = await read_recording_device(
                db, UUID(actor.user_id), runtime.context.application_origin
            )
    except CommandRejected as error:
        return UnifiedToolOutput.failure(
            message="Device observation unavailable.", error_code=error.code
        )
    except AuthorizationError as error:
        return UnifiedToolOutput.failure(
            message="Device observation unavailable.",
            error_code=application_access_error_code(error),
        )
    except SQLAlchemyError, RedisError, OSError:
        return UnifiedToolOutput.failure(
            message="Device observation unavailable.", error_code="DEPENDENCY_ERROR"
        )
    return UnifiedToolOutput.data_success(
        message="Observed device-reported recorder state at the stated time; not server completion.",
        structured_data={"device_reported": True, **snapshot.model_dump(mode="json")},
    )
