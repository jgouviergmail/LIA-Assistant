"""Saved location reads and exact home-location confirmation through the domain owner."""

from typing import Annotated
from uuid import UUID

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, BaseAPIException
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.location_preparation import prepare_location_change
from src.domains.agents.application.location_queries import read_locations
from src.domains.agents.application.location_schemas import (
    LocationChangeRequest,
    LocationField,
    LocationRead,
)
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


@read_tool(name="get_lia_locations", agent_name="setting_agent")
async def get_lia_locations_tool(
    fields: Annotated[list[LocationField] | None, LocationRead.model_fields["fields"]] = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read saved home and last-known account positions, with their stored timestamp.

    Args:
        fields: Distinct saved location selectors; omit to read both.
        runtime: Injected authenticated account context.

    Returns:
        Saved account locations. Current browser coordinates are obtained separately.
    """
    validated = validate_runtime_config(runtime, "get_lia_locations_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    try:
        request = LocationRead(fields=fields)
        async with get_db_context() as db:
            projection = await read_locations(db, UUID(str(validated.user_id)), request)
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Invalid location selection.", error_code="INVALID_INPUT"
        )
    except ValueError:
        return UnifiedToolOutput.failure(
            message="Saved location is unavailable.", error_code="INVALID_STORED_DATA"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Application access refused.", error_code=application_access_error_code(exc)
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Application state unavailable.", error_code="DEPENDENCY_ERROR"
        )
    return UnifiedToolOutput.data_success(
        message="Saved account locations.",
        structured_data={
            "preferences": projection.model_dump(mode="json"),
            "total": len(projection.values),
        },
    )


@write_tool(name="update_lia_home_location", agent_name="setting_agent")
async def update_lia_home_location_tool(
    change: LocationChangeRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Resolve an address and prepare exact HITL; clear also removes the saved position.

    Args:
        change: Set with the person's address, or clear with no address. Never invent coordinates.
        runtime: Injected account context; the model cannot select an actor.

    Returns:
        A durable confirmation of resolved home data and all deletion consequences.
    """
    validated = validate_runtime_config(runtime, "update_lia_home_location_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    assert runtime is not None
    try:
        async with get_db_context() as db:
            content = await prepare_location_change(db, UUID(validated.user_id), change)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="update_lia_home_location_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid or unavailable home location.", error_code="INVALID_INPUT"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Application access refused.", error_code=application_access_error_code(exc)
        )
    except BaseAPIException:
        return UnifiedToolOutput.failure(
            message="Home location preparation was refused.", error_code="PREPARATION_REFUSED"
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="The proposal could not be persisted.", error_code="DEPENDENCY_ERROR"
        )
    return output
