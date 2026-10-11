"""Compatibility parsing ends in the same exact native creation proposal."""

from uuid import UUID

from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.core.exceptions import ValidationError as DomainValidationError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.workboard_create import (
    creation_access,
    prepare_workboard_creation,
)
from src.domains.agents.application.workboard_create_schemas import WorkboardCreateInput
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import get_user_preferences, validate_runtime_config
from src.domains.agents.tools.workboard_legacy_input import normalize_workboard_legacy
from src.domains.workboard.service import WorkboardService
from src.infrastructure.database.session import get_db_context


async def _legacy_request(
    db: AsyncSession, owner_id: UUID, zone: str, values: dict[str, object]
) -> WorkboardCreateInput:
    service = WorkboardService(db)
    values = await normalize_workboard_legacy(service, owner_id, zone, values)
    return WorkboardCreateInput.model_validate(values)


async def _selected_request(
    db: AsyncSession,
    owner: UUID,
    runtime: ToolRuntime[LiaRuntimeContext, object],
    request: WorkboardCreateInput | None,
    legacy: dict[str, object],
) -> WorkboardCreateInput:
    if request is not None:
        parsed = WorkboardCreateInput.model_validate(request)
        return WorkboardCreateInput.model_validate(parsed.model_dump())
    zone, _, _ = await get_user_preferences(runtime)
    return await _legacy_request(db, owner, zone, legacy)


async def propose_workboard_creation(
    runtime: ToolRuntime[LiaRuntimeContext, object] | None,
    request: WorkboardCreateInput | None,
    values: dict[str, object],
) -> UnifiedToolOutput:
    actor = validate_runtime_config(runtime, "create_ticket_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    legacy = {key: value for key, value in values.items() if value is not None}
    if request is not None and legacy:
        return UnifiedToolOutput.failure(
            message="Use the full request or legacy fields, not both.", error_code="INVALID_INPUT"
        )
    owner = UUID(actor.user_id)
    try:
        async with get_db_context() as db:
            await creation_access(db, owner)
            selected = await _selected_request(db, owner, runtime, request, legacy)
            content = await prepare_workboard_creation(db, owner, selected)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="create_ticket_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Workboard proposal refused.", error_code=application_access_error_code(exc)
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(
            message="Selected parent or assignee unavailable.",
            error_code="NOT_FOUND_OR_UNAUTHORIZED",
        )
    except DomainValidationError as exc:
        code = str(exc.detail)
        return UnifiedToolOutput.failure(
            message=code, error_code="CONSTRAINT_VIOLATION", metadata={"workboard_error": code}
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Workboard proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid Workboard configuration.", error_code="INVALID_INPUT"
        )
    return output
