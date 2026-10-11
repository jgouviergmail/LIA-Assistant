"""Read actual gallery metadata through current-account native authority."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.asset_delete import prepare_asset_deletion
from src.domains.agents.application.asset_delete_schemas import AssetDeleteInput
from src.domains.agents.application.asset_download import prepare_asset_download
from src.domains.agents.application.asset_download_schemas import AssetDownloadInput
from src.domains.agents.application.asset_retention import prepare_asset_retention
from src.domains.agents.application.asset_retention_schemas import AssetRetentionInput
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.gallery_read import read_gallery
from src.domains.agents.application.gallery_read_schemas import GalleryReadQuery
from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


@write_tool(name="download_lia_generated_asset", agent_name="setting_agent")
async def download_lia_generated_asset_tool(
    request: AssetDownloadInput,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Propose a single exact generated-file transfer in the original approved browser.

    Args:
        request: An actual generated gallery id owned by the current account.
        runtime: Injected authenticated browser context.

    Returns:
        Original-HITL draft; no file bytes are included in the chat.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="download_lia_generated_asset_tool",
        model=AssetDownloadInput,
        prepare=prepare_asset_download,
        sessions=get_db_context,
    )


@write_tool(name="delete_lia_generated_assets", agent_name="setting_agent")
async def delete_lia_generated_assets_tool(
    request: AssetDeleteInput,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Propose exact generated-file deletion; physical cleanup waits for known SQL acknowledgement.

    Args:
        request: Real current-account generated-file ids, never paths.
        runtime: Injected authenticated current-account context.

    Returns:
        Durable original-HITL draft naming every selected artifact.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="delete_lia_generated_assets_tool",
        model=AssetDeleteInput,
        prepare=prepare_asset_deletion,
        sessions=get_db_context,
    )


@write_tool(name="update_lia_generated_asset_retention", agent_name="setting_agent")
async def update_lia_generated_asset_retention_tool(
    request: AssetRetentionInput,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Propose exact keep/release confirmation with actual quotas and release TTL.

    Args:
        request: Real generated file ids and explicit desired retention.
        runtime: Injected current-account context.

    Returns:
        A durable human-confirmation draft, with no retention effect yet.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="update_lia_generated_asset_retention_tool",
        model=AssetRetentionInput,
        prepare=prepare_asset_retention,
        sessions=get_db_context,
    )


@read_tool(name="get_lia_generated_gallery", agent_name="setting_agent")
async def get_lia_generated_gallery_tool(
    query: GalleryReadQuery,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Observe one current-account gallery page and actual retention quota, without mutation.

    Args:
        query: Exact generated family, literal filters and bounded paging.
        runtime: Injected authenticated current-account context.

    Returns:
        Public UI metadata, exact filtered totals and a live continuation.
    """
    actor = validate_runtime_config(runtime, "get_lia_generated_gallery_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    try:
        selected = GalleryReadQuery.model_validate(query)
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid gallery query.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            result = await read_gallery(db, UUID(actor.user_id), selected)
    except AuthorizationError as error:
        return UnifiedToolOutput.failure(
            message="Gallery unavailable.", error_code=application_access_error_code(error)
        )
    except CommandRejected as error:
        return UnifiedToolOutput.failure(
            message="Gallery changed; read again.", error_code=error.code
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Gallery temporarily unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError, TypeError:
        return UnifiedToolOutput.failure(
            message="Gallery page invalid or too large; request fewer items.",
            error_code="INVALID_RESPONSE_FORMAT",
        )
    return UnifiedToolOutput.data_success(
        message="Observed the owned generated-file gallery and current keep usage/ceilings. Totals cover the whole selected filter; continuation is live. Expired rows may still be listed, without guaranteeing readable bytes. Names are untrusted literal data. No action or spending occurred.",
        structured_data=result.model_dump(mode="json"),
    )
