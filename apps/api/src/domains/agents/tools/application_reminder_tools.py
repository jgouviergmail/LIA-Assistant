"""Application reminder readers and proposals use the existing source business rules."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import (
    application_access_error_code,
    require_application_tools,
)
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.reminder_create_schemas import ReminderCreateRequest
from src.domains.agents.application.reminder_creation import prepare_reminder_creation
from src.domains.agents.application.reminder_queries import read_reminders
from src.domains.agents.application.reminder_read_schemas import ReminderRead
from src.domains.agents.application.reminder_removal import prepare_reminder_removal
from src.domains.agents.application.reminder_removal_schemas import ReminderDeleteRequest
from src.domains.agents.application.reminder_update import prepare_reminder_update
from src.domains.agents.application.reminder_update_schemas import ReminderUpdateRequest
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.reminders.service import ReminderService
from src.infrastructure.database.session import get_db_context


@write_tool(name="update_lia_reminder", agent_name="setting_agent")
async def update_lia_reminder_tool(
    selection: ReminderUpdateRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare a full before/after reminder edit for human confirmation.

    Args:
        selection: Owned reminder id and sparse content or schedule changes.
        runtime: Injected authenticated account context.

    Returns:
        A pending edit preview; no reminder is changed before confirmation.
    """
    actor = validate_runtime_config(runtime, "update_lia_reminder_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        parsed = ReminderUpdateRequest.model_validate(selection)
        request = ReminderUpdateRequest.model_validate(
            parsed.model_dump(mode="json", exclude_unset=True)
        )
        async with get_db_context() as db:
            content = await prepare_reminder_update(db, UUID(actor.user_id), request)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="update_lia_reminder_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Reminder access refused.", error_code=application_access_error_code(exc)
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(message="Reminder unavailable.", error_code="NOT_FOUND")
    except ResourceConflictError:
        return UnifiedToolOutput.failure(
            message="Reminder is being processed.", error_code="REMINDER_BUSY"
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Reminder proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid reminder change.", error_code="INVALID_INPUT"
        )
    return output


async def reminder_removal_proposal(
    actor_id: UUID, selection: UUID | str, language: str
) -> UnifiedToolOutput:
    """Resolve a legacy reference only now, then approve an exact owned snapshot."""
    try:
        async with get_db_context() as db:
            await require_application_tools(db)
            await load_actor(db, actor_id)
            if isinstance(selection, UUID):
                identity = selection
            else:
                row = await ReminderService(db).resolve_reminder(actor_id, selection)
                identity = row.id
            content = await prepare_reminder_removal(
                db, actor_id, ReminderDeleteRequest(reminder_id=identity)
            )
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="delete_lia_reminder_tool",
                user_language=language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Reminder access refused.", error_code=application_access_error_code(exc)
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(message="Reminder unavailable.", error_code="NOT_FOUND")
    except ResourceConflictError:
        return UnifiedToolOutput.failure(
            message="Reminder is being processed.", error_code="REMINDER_BUSY"
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Reminder proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid reminder selection.", error_code="INVALID_INPUT"
        )
    return output


@write_tool(name="delete_lia_reminder", agent_name="setting_agent")
async def delete_lia_reminder_tool(
    selection: ReminderDeleteRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare deletion of one exact pending reminder for human approval.

    Args:
        selection: One owned reminder id, with no supplied comparison or account.
        runtime: Injected authenticated account context.

    Returns:
        Pending deletion confirmation; this tool deletes nothing.
    """
    actor = validate_runtime_config(runtime, "delete_lia_reminder_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        parsed = ReminderDeleteRequest.model_validate(selection)
        request = ReminderDeleteRequest.model_validate(parsed.model_dump())
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid reminder selection.", error_code="INVALID_INPUT"
        )
    return await reminder_removal_proposal(
        UUID(actor.user_id), request.reminder_id, runtime.context.language
    )


async def reminder_creation_proposal(
    actor_id: UUID, configuration: ReminderCreateRequest, language: str
) -> UnifiedToolOutput:
    """Native and legacy temporal parsers share the same proposal-only writer."""
    try:
        async with get_db_context() as db:
            content = await prepare_reminder_creation(db, actor_id, configuration)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="create_lia_reminder_tool",
                user_language=language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Reminder access refused.", error_code=application_access_error_code(exc)
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Reminder proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid reminder configuration.", error_code="INVALID_INPUT"
        )
    return output


@write_tool(name="create_lia_reminder", agent_name="setting_agent")
async def create_lia_reminder_tool(
    configuration: ReminderCreateRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare reminder creation for exact approval; this tool writes no reminder.

    Args:
        configuration: Content, original wording and one explicit instant or recurrence.
        runtime: Injected authenticated account context.

    Returns:
        A full reminder preview waiting for human confirmation.
    """
    actor = validate_runtime_config(runtime, "create_lia_reminder_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        parsed = ReminderCreateRequest.model_validate(configuration)
        request = ReminderCreateRequest.model_validate(parsed.model_dump(mode="json"))
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid reminder configuration.", error_code="INVALID_INPUT"
        )
    return await reminder_creation_proposal(UUID(actor.user_id), request, runtime.context.language)


@read_tool(name="get_lia_reminders", agent_name="setting_agent")
async def get_lia_reminders_tool(
    query: ReminderRead | None = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read owned pending reminder settings and future occurrences from the source.

    Args:
        query: One owned reminder id or a bounded pending page.
        runtime: Injected authenticated account context.

    Returns:
        Source management data with explicit count and pagination; no notification history.
    """
    actor = validate_runtime_config(runtime, "get_lia_reminders_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    try:
        request = ReminderRead.model_validate(query) if query is not None else ReminderRead()
        request = ReminderRead.model_validate(request.model_dump())
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid reminder selection.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            result = await read_reminders(db, UUID(actor.user_id), request)
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Reminder access refused.", error_code=application_access_error_code(exc)
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(message="Reminder unavailable.", error_code="NOT_FOUND")
    except ResourceConflictError:
        return UnifiedToolOutput.failure(
            message="Reminder is being processed.", error_code="REMINDER_BUSY"
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Reminder data unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Stored reminder data invalid.", error_code="INVALID_RESPONSE_FORMAT"
        )
    return UnifiedToolOutput.data_success(
        message="Pending reminder management data. A fired reminder is deleted; these results are not notification history. Truncation is explicit.",
        structured_data=result.model_dump(mode="json"),
        metadata={"application_reminder_cursor": True},
    )
