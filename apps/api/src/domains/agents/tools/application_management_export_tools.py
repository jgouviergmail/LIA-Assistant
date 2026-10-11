"""Management exports require an exact proposal and the original authenticated browser."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.management_export import prepare_management_export
from src.domains.agents.application.management_export_schemas import ManagementExportRequest
from src.domains.agents.application.management_export_sources import MANAGEMENT_EXPORT_SOURCES
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


@write_tool(name="export_lia_interests", agent_name="setting_agent")
async def export_lia_interests_tool(
    request: ManagementExportRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact human confirmation for an export of all owned saved interests.

    Args:
        request: CSV or JSON format; defaults to the management UI's CSV format.
        runtime: Injected authenticated browser account context.

    Returns:
        Bounded complete-scope preview, without a file or source text in chat.
        After approval, start one download in the original browser. A request is not a saved file.
    """
    return await _prepare_export_tool(request, runtime, "interests.export")


@write_tool(name="export_lia_memories", agent_name="setting_agent")
async def export_lia_memories_tool(
    request: ManagementExportRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact confirmation to export all current owned memories in CSV or JSON.

    Args:
        request: Source CSV or JSON format; defaults to CSV.
        runtime: Injected authenticated browser account context.

    Returns:
        Bounded exact preview. No memory text, vectors, biometric context or file before approval.
        Superseded memories stay outside this management export. One original-browser request follows approval.
    """
    return await _prepare_export_tool(request, runtime, "memories.export")


@write_tool(name="export_lia_journals", agent_name="setting_agent")
async def export_lia_journals_tool(
    request: ManagementExportRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare confirmation to download all owned journal entries and the stored JSON portrait.

    Args:
        request: CSV or JSON; CSV defaults, JSON also includes the stored portrait.
        runtime: Injected original authenticated browser context.

    Returns:
        Count and format only before approval. Active and archived entries are included.
        JSON preserves the stored portrait even when stale or personal learning is disabled.
        No provider call or file content in chat. Approval permits one original-browser request.
    """
    return await _prepare_export_tool(request, runtime, "journals.export")


async def _prepare_export_tool(
    request: ManagementExportRequest,
    runtime: ToolRuntime[LiaRuntimeContext, object] | None,
    operation_id: str,
) -> UnifiedToolOutput:
    source = MANAGEMENT_EXPORT_SOURCES[operation_id]
    actor = validate_runtime_config(runtime, source.operation.tool_name)
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        parsed = ManagementExportRequest.model_validate(request)
        selected = ManagementExportRequest.model_validate(parsed.model_dump())
        async with get_db_context() as db:
            content = await prepare_management_export(
                db,
                UUID(actor.user_id),
                selected,
                operation_id,
                origin=runtime.context.application_origin,
            )
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool=source.operation.tool_name,
                user_language=runtime.context.language,
            )
            await save_command(
                db,
                content,
                next(iter(output.registry_updates)),
                origin=runtime.context.application_origin,
            )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Export access refused.", error_code=application_access_error_code(exc)
        )
    except SQLAlchemyError, RedisError:
        return UnifiedToolOutput.failure(
            message="Export proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid export format or source data.", error_code="INVALID_INPUT"
        )
    return output
