"""Native psyche resets are proposals only until exact durable human approval."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.psyche_reset import prepare_psyche_reset
from src.domains.agents.application.psyche_reset_schemas import PsycheResetIntent
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


@write_tool(name="reset_lia_psyche", agent_name="setting_agent")
async def reset_lia_psyche_tool(
    request: PsycheResetIntent,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact confirmation for soft, full or complete owned psyche purge.

    Args:
        request: Source reset level; private scope is reconstructed by the server.
        runtime: Injected authenticated account context.

    Returns:
        Pending source-derived before/after confirmation without writing any state.
    """
    actor = validate_runtime_config(runtime, "reset_lia_psyche_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        selected = PsycheResetIntent.model_validate(request)
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid psyche reset level.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            content = await prepare_psyche_reset(db, UUID(actor.user_id), selected)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="reset_lia_psyche_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Psyche reset refused.", error_code=application_access_error_code(exc)
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Psyche reset proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Stored psyche reset scope invalid.", error_code="INVALID_RESPONSE_FORMAT"
        )
    return output
