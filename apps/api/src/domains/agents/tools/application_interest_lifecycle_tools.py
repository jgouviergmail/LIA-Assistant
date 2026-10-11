"""Owned interest lifecycle actions prepare mandatory confirmation through the shared source."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.interest_reactivation import prepare_interest_reactivation
from src.domains.agents.application.interest_reactivation_schemas import InterestReactivateRequest
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


@write_tool(name="reactivate_lia_interest", agent_name="setting_agent")
async def reactivate_lia_interest_tool(
    selection: InterestReactivateRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact human confirmation to reactivate one owned dormant interest.

    Args:
        selection: One owned dormant identity obtained from the interest management reader.
        runtime: Injected authenticated account context.

    Returns:
        Complete source reset preview; no reactivation, model or embedding call before approval.
    """
    actor = validate_runtime_config(runtime, "reactivate_lia_interest_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        parsed = InterestReactivateRequest.model_validate(selection)
        request = InterestReactivateRequest.model_validate(parsed.model_dump())
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid interest identity.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            content = await prepare_interest_reactivation(db, UUID(actor.user_id), request)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="reactivate_lia_interest_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(message="Interest unavailable.", error_code="NOT_FOUND")
    except ResourceConflictError:
        return UnifiedToolOutput.failure(
            message="Only a dormant interest can be reactivated.", error_code="CONFLICT"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Interest access refused.", error_code=application_access_error_code(exc)
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Reactivation proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Stored interest state invalid.", error_code="INVALID_RESPONSE_FORMAT"
        )
    return output
