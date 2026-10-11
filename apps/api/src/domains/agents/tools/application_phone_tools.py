"""Read saved phone identity and effective mode without placing a verification call."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.phone_number_operations import prepare_phone_number
from src.domains.agents.application.phone_number_schemas import PhoneNumberRequest
from src.domains.agents.application.phone_operations import read_phone_identity
from src.domains.agents.application.phone_preference_operations import prepare_phone_preferences
from src.domains.agents.application.phone_preference_schemas import PhonePreferenceRequest
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


@read_tool(name="get_lia_phone_identity", agent_name="setting_agent")
async def get_lia_phone_identity_tool(
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read this user's phone number, verification state, enabled domains and saved/effective mode.

    Args:
        runtime: Injected authenticated account context.

    Returns:
        Reviewed phone identity UI data and number_status: unset, available or unreadable.
        Verification is for a readable line; unreadable is not absence of a saved number.
        Read-only pending state: no dial, OTP, deletion, new verification or key exposure.
    """
    actor = validate_runtime_config(runtime, "get_lia_phone_identity_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    try:
        async with get_db_context() as db:
            result = await read_phone_identity(db, UUID(actor.user_id))
    except RedisError, SQLAlchemyError, OSError:
        return UnifiedToolOutput.failure(
            message="Phone identity unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Phone identity unavailable.", error_code=application_access_error_code(exc)
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(
            message="Phone identity unavailable.", error_code="FORBIDDEN"
        )
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Saved phone identity invalid.", error_code="INVALID_RESPONSE_FORMAT"
        )
    except ValueError:
        return UnifiedToolOutput.failure(
            message="Saved phone identity invalid.", error_code="INVALID_RESPONSE_FORMAT"
        )
    return UnifiedToolOutput.data_success(
        message="Saved phone identity and effective call mode, with read-only pending verification state. An unreadable number is a saved record that cannot currently be used, not an unset number. No verification call, secure code or settings change.",
        structured_data=result.model_dump(mode="json"),
    )


@write_tool(name="update_lia_phone_number", agent_name="setting_agent")
async def update_lia_phone_number_tool(
    change: PhoneNumberRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare an exact confirmation to set or clear the account's declared number.

    Args:
        change: Set with a number, or clear without a number. Source normalization is shown.
        runtime: Injected authenticated account context.

    Returns:
        Durable proposal only. Changed numbers lose verification; the same number preserves it.
        No verification call, proof or settings write before confirmation. Future owner calls use
        the saved number; running calls continue under their existing mandate.
    """
    actor = validate_runtime_config(runtime, "update_lia_phone_number_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        parsed = PhoneNumberRequest.model_validate(change)
        request = PhoneNumberRequest.model_validate(parsed.model_dump(exclude_unset=True))
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Invalid number change.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            content = await prepare_phone_number(db, UUID(actor.user_id), request)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="update_lia_phone_number_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Number proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Number proposal unavailable.", error_code=application_access_error_code(exc)
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Saved number state invalid.", error_code="INVALID_RESPONSE_FORMAT"
        )
    return output


@write_tool(name="update_lia_phone_preferences", agent_name="setting_agent")
async def update_lia_phone_preferences_tool(
    change: PhonePreferenceRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact confirmation of phone context consent, disabled domains and saved call mode.

    Args:
        change: Explicit non-null context consent, domain replacement or direct/delegated mode.
        runtime: Injected authenticated account context.

    Returns:
        Durable proposal; no write, verification, provider request or call. Mode/context apply to
        future owner calls. Domain refusals apply at the next phone/direct-browser lookup, including
        running sessions; browser setup declarations refresh at start/wake. Read get_lia_phone_identity
        for available domains and effective mode. Empty list enables every offered domain.
    """
    actor = validate_runtime_config(runtime, "update_lia_phone_preferences_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        request = PhonePreferenceRequest.model_validate(change)
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Invalid phone settings change.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            content = await prepare_phone_preferences(db, UUID(actor.user_id), request)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="update_lia_phone_preferences_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Phone proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Phone proposal unavailable.", error_code=application_access_error_code(exc)
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Saved phone settings invalid.", error_code="INVALID_RESPONSE_FORMAT"
        )
    return output
