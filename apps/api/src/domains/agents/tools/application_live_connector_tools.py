"""Saved Live provider settings with mandatory exact confirmation before provider work."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.live_connector_operations import (
    prepare_live_connector_content,
    read_live_connector_preferences,
)
from src.domains.agents.application.live_connector_schemas import LiveConnectorChangeRequest
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context
from src.infrastructure.live_connector_preferences import LiveConnectorSettingsRefused


@read_tool(name="get_lia_live_connector_settings", agent_name="setting_agent")
async def get_lia_live_connector_settings_tool(
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read saved Live providers and their model, voice, thinking, durations and budget.

    Args:
        runtime: Injected authenticated account context.

    Returns:
        Saved settings and effective capabilities; no provider discovery, credentials or session start.
    """
    actor = validate_runtime_config(runtime, "get_lia_live_connector_settings_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    try:
        async with get_db_context() as db:
            result = await read_live_connector_preferences(db, UUID(actor.user_id))
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Live settings unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Live management unavailable.", error_code=application_access_error_code(exc)
        )
    except LiveConnectorSettingsRefused as exc:
        return UnifiedToolOutput.failure(message="Live connector unavailable.", error_code=exc.code)
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Saved Live settings unavailable.", error_code="INVALID_RESPONSE_FORMAT"
        )
    return UnifiedToolOutput.data_success(
        message="Saved Live provider settings. The budget is indicative per session on your own provider key. Current session state and provider discovery are separate.",
        structured_data=result.model_dump(mode="json"),
    )


@write_tool(name="update_lia_live_connector_settings", agent_name="setting_agent")
async def update_lia_live_connector_settings_tool(
    change: LiveConnectorChangeRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare confirmation of requested Live provider settings; preserve omitted settings.

    Args:
        change: Existing provider and explicit non-secret settings delta.
        runtime: Injected authenticated account context.

    Returns:
        Pending exact confirmation; a provider probe only follows approval on the saved key.
    """
    actor = validate_runtime_config(runtime, "update_lia_live_connector_settings_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        request = LiveConnectorChangeRequest.model_validate(change)
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Invalid Live settings request.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            content = await prepare_live_connector_content(db, UUID(actor.user_id), request)
            draft = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="update_lia_live_connector_settings_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(draft.registry_updates)))
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Live proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Live management unavailable.", error_code=application_access_error_code(exc)
        )
    except LiveConnectorSettingsRefused as exc:
        return UnifiedToolOutput.failure(message="Live connector unavailable.", error_code=exc.code)
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Saved Live settings unavailable.", error_code="INVALID_RESPONSE_FORMAT"
        )
    return draft
