"""Saved live conversation reflexes; no credential, model probe or live session action."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.live_operations import (
    prepare_live_preference_content,
    read_live_preferences,
)
from src.domains.agents.application.live_schemas import LivePreferenceRequest
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


@read_tool(name="get_lia_live_preferences", agent_name="setting_agent")
async def get_lia_live_preferences_tool(
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read saved live reflexes: interruptions, pause sensitivity and result delivery.

    Args:
        runtime: Injected authenticated account context.

    Returns:
        Effective saved account values for future sessions; no current-session reconfiguration.
    """
    validated = validate_runtime_config(runtime, "get_lia_live_preferences_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    try:
        async with get_db_context() as db:
            result = await read_live_preferences(db, UUID(validated.user_id))
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Live settings unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Saved live settings unavailable.", error_code="INVALID_RESPONSE_FORMAT"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Application management unavailable.",
            error_code=application_access_error_code(exc),
        )
    return UnifiedToolOutput.data_success(
        message="Effective saved live reflexes for future sessions. Provider/model choices and current session state are separate.",
        structured_data=result.model_dump(mode="json"),
    )


@write_tool(name="update_lia_live_preferences", agent_name="setting_agent")
async def update_lia_live_preferences_tool(
    change: LivePreferenceRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact confirmation of requested live reflex changes; preserve all other values.

    Args:
        change: Requested interruptions, pause sensitivity or result delivery values.
        runtime: Injected authenticated account context.

    Returns:
        Durable proposal for future sessions. No session starts and no saved value changes yet.
    """
    validated = validate_runtime_config(runtime, "update_lia_live_preferences_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    assert runtime is not None
    try:
        request = LivePreferenceRequest.model_validate(change)
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Invalid live preference change.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            content = await prepare_live_preference_content(db, UUID(validated.user_id), request)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="update_lia_live_preferences_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Live proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Saved live settings unavailable.",
            error_code="INVALID_RESPONSE_FORMAT",
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Application management unavailable.",
            error_code=application_access_error_code(exc),
        )
    return output
