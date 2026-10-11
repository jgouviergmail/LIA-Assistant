"""Saved notification device tools never acquire or expose push credentials."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.notification_operations import (
    prepare_notification_device_removal,
    read_notification_devices,
)
from src.domains.agents.application.notification_schemas import (
    NotificationDeviceRemoveRequest,
    NotificationDevicesRead,
)
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context
from src.infrastructure.notification_devices import NotificationDeviceUnavailable


@read_tool(name="get_lia_notification_devices", agent_name="setting_agent")
async def get_lia_notification_devices_tool(
    query: NotificationDevicesRead | None = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read saved notification registrations; browser/system permission is separate.

    Args:
        query: Selected owned device or bounded page; next_cursor continues as after_id.
        runtime: Injected authenticated account context.

    Returns:
        Saved device identities and activity, without push credentials or delivery guarantees.
    """
    validated = validate_runtime_config(runtime, "get_lia_notification_devices_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    try:
        request = (
            NotificationDevicesRead.model_validate(query)
            if query is not None
            else NotificationDevicesRead()
        )
        async with get_db_context() as db:
            values = await read_notification_devices(db, UUID(validated.user_id), request)
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Notification devices unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except NotificationDeviceUnavailable:
        return UnifiedToolOutput.failure(
            message="Saved notification device unavailable.",
            error_code=ToolErrorCode.INVALID_RESPONSE_FORMAT,
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid notification device request.", error_code="INVALID_INPUT"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Application management unavailable.",
            error_code=application_access_error_code(exc),
        )
    return UnifiedToolOutput.data_success(
        message="Saved notification devices. Active registration is not browser/system permission or guaranteed delivery. Follow next_cursor for every page.",
        structured_data=values.model_dump(mode="json"),
        metadata={"application_notification_cursor": True},
    )


@write_tool(name="remove_lia_notification_device", agent_name="setting_agent")
async def remove_lia_notification_device_tool(
    change: NotificationDeviceRemoveRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact human confirmation to remove one saved notification device.

    Args:
        change: Owned saved device id. Removal leaves browser/system permission unchanged.
        runtime: Injected authenticated account context.

    Returns:
        Durable proposal; no removal before confirmation and no credential in public intent.
    """
    validated = validate_runtime_config(runtime, "remove_lia_notification_device_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    assert runtime is not None
    try:
        request = NotificationDeviceRemoveRequest.model_validate(change)
        async with get_db_context() as db:
            content = await prepare_notification_device_removal(
                db, UUID(validated.user_id), request
            )
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="remove_lia_notification_device_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Notification device proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except NotificationDeviceUnavailable:
        return UnifiedToolOutput.failure(
            message="Saved notification device unavailable.",
            error_code=ToolErrorCode.INVALID_RESPONSE_FORMAT,
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid notification device change.", error_code="INVALID_INPUT"
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(
            message="Notification device unavailable.", error_code="NOT_FOUND"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Application management unavailable.",
            error_code=application_access_error_code(exc),
        )
    return output
