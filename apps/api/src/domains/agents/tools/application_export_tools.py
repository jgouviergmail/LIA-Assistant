"""Account export status and confirmed requests, without archive paths or content."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.export_action import prepare_account_export
from src.domains.agents.application.export_download import prepare_export_download
from src.domains.agents.application.export_download_schemas import ExportDownloadRequest
from src.domains.agents.application.export_operations import read_export_settings
from src.domains.agents.context.runtime_context import LiaRuntimeContext, tool_runtime_context
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


@write_tool(name="download_lia_account_export", agent_name="setting_agent")
async def download_lia_account_export_tool(
    selection: ExportDownloadRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact confirmation to start an owned archive download in the original browser.

    Args:
        selection: One owned completed export job id; no path or URL.
        runtime: Injected authenticated browser context.

    Returns:
        A pending confirmation. No archive bytes or download audit are produced here.
        Browser initiation does not prove that a file was saved to the device.
    """
    actor = validate_runtime_config(runtime, "download_lia_account_export_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    context = tool_runtime_context(runtime)
    if context is None:
        return UnifiedToolOutput.failure(
            message="Authenticated browser required.", error_code="FORBIDDEN"
        )
    try:
        parsed = ExportDownloadRequest.model_validate(selection)
        request = ExportDownloadRequest.model_validate(parsed.model_dump())
        async with get_db_context() as db:
            content = await prepare_export_download(
                db, UUID(actor.user_id), request, origin=context.application_origin
            )
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="download_lia_account_export_tool",
                user_language=context.language,
            )
            await save_command(
                db, content, next(iter(output.registry_updates)), origin=context.application_origin
            )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(message="Archive unavailable.", error_code="NOT_FOUND")
    except ResourceConflictError:
        return UnifiedToolOutput.failure(
            message="Archive changed; select it again.", error_code="STALE_STATE"
        )
    except SQLAlchemyError, RedisError, OSError:
        return UnifiedToolOutput.failure(
            message="Download proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Download unavailable.", error_code=application_access_error_code(exc)
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid download selection.", error_code="INVALID_INPUT"
        )
    return output


@read_tool(name="get_lia_account_export", agent_name="setting_agent")
async def get_lia_account_export_tool(
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read account-export feature availability, the latest saved job and download availability.

    Args:
        runtime: Injected authenticated account context.

    Returns:
        Owned saved job metadata only. A done job is downloadable only within retention with its file.
        No new job, download audit increment, archive content, local path or secure reauthentication.
    """
    actor = validate_runtime_config(runtime, "get_lia_account_export_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    try:
        async with get_db_context() as db:
            result = await read_export_settings(db, UUID(actor.user_id))
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Export state unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Export state unavailable.", error_code=application_access_error_code(exc)
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Saved export state unavailable.", error_code="INVALID_RESPONSE_FORMAT"
        )
    return UnifiedToolOutput.data_success(
        message="Latest saved account export. Use download_available, not done status alone: retention or a missing file can prevent download. This read never creates or downloads an archive.",
        structured_data=result.model_dump(mode="json"),
    )


@write_tool(name="request_lia_account_export", agent_name="setting_agent")
async def request_lia_account_export_tool(
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare confirmation for a full-account export, then secure browser reauthentication.

    No job starts during preparation. Never request credentials in chat.
    A queued job is not a ready archive; read its status and availability before proposing download.
    """
    actor = validate_runtime_config(runtime, "request_lia_account_export_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    context = tool_runtime_context(runtime)
    if context is None:
        return UnifiedToolOutput.failure(
            message="Authenticated browser required.", error_code="FORBIDDEN"
        )
    try:
        async with get_db_context() as db:
            content = await prepare_account_export(
                db, UUID(actor.user_id), origin=context.application_origin
            )
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="request_lia_account_export_tool",
                user_language=context.language,
            )
            await save_command(
                db, content, next(iter(output.registry_updates)), origin=context.application_origin
            )
    except SQLAlchemyError, RedisError, OSError:
        return UnifiedToolOutput.failure(
            message="Export proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Export unavailable.", error_code=application_access_error_code(exc)
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid export request.", error_code="INVALID_INPUT"
        )
    return output
