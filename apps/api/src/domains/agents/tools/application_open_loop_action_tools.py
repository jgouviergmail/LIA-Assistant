"""Native commitment adapters only create exact human-confirmation proposals."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.open_loop_action_schemas import (
    OpenLoopCloseRequest,
    OpenLoopUpdateRequest,
)
from src.domains.agents.application.open_loop_actions import prepare_open_loop_action
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


async def _prepare(
    request: object,
    runtime: ToolRuntime[LiaRuntimeContext, object] | None,
    source_tool: str,
    model: type[OpenLoopUpdateRequest] | type[OpenLoopCloseRequest],
) -> UnifiedToolOutput:
    actor = validate_runtime_config(runtime, source_tool)
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        parsed = model.model_validate(request)
        parsed = model.model_validate(parsed.model_dump(mode="json", exclude_unset=True))
        async with get_db_context() as db:
            content = await prepare_open_loop_action(db, UUID(actor.user_id), parsed)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool=source_tool,
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
        return output
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(message="Commitment unavailable.", error_code="NOT_FOUND")
    except ResourceConflictError:
        return UnifiedToolOutput.failure(
            message="Only an open owned commitment can be changed.", error_code="CONFLICT"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Commitment access refused.", error_code=application_access_error_code(exc)
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Commitment proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid commitment request or source state.", error_code="INVALID_INPUT"
        )


@write_tool(name="update_lia_open_loop", agent_name="setting_agent")
async def update_lia_open_loop_tool(
    request: OpenLoopUpdateRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact human confirmation of an owned commitment wording/deadline correction.

    Args:
        request: Owned loop identity and sparse source correction.
        runtime: Injected authenticated account context.

    Returns:
        Complete source before/after confirmation; no mutation before approval.
    """
    return await _prepare(request, runtime, "update_lia_open_loop_tool", OpenLoopUpdateRequest)


@write_tool(name="close_lia_open_loop", agent_name="setting_agent")
async def close_lia_open_loop_tool(
    request: OpenLoopCloseRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact human confirmation to mark an owned commitment done or no longer relevant.

    Args:
        request: Owned loop identity and source closure action.
        runtime: Injected authenticated account context.

    Returns:
        Complete source lifecycle confirmation; no closure before approval.
    """
    return await _prepare(request, runtime, "close_lia_open_loop_tool", OpenLoopCloseRequest)
