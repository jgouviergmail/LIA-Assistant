"""Read the account's retained call rows and observed recorded platform usage."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.phone_history_operations import read_phone_history
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import read_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.telephony.history_schemas import PhoneHistoryRead
from src.infrastructure.database.session import get_db_context


@read_tool(name="get_lia_phone_calls", agent_name="setting_agent")
async def get_lia_phone_calls_tool(
    query: PhoneHistoryRead | None = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read owned retained calls, their statuses, recaps and observed recorded platform usage.

    Args:
        query: Bounded page; continue with the last shown next_cursor.
        runtime: Injected authenticated account context.

    Returns:
        The same reviewed public call rows as the interface, never encrypted callee numbers.
        usage_scope is recorded_platform_runs: absent usage does not mean a free call;
        purged message associations may omit delegated runs, and vendor invoices are separate.
        No call, synthesis, refund, provider lookup, record purge or mutation.
    """
    actor = validate_runtime_config(runtime, "get_lia_phone_calls_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    try:
        request = (
            PhoneHistoryRead.model_validate(query) if query is not None else PhoneHistoryRead()
        )
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Invalid call history query.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            result = await read_phone_history(db, UUID(actor.user_id), request)
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Call history unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Call history unavailable.", error_code=application_access_error_code(exc)
        )
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Saved call history invalid.", error_code="INVALID_RESPONSE_FORMAT"
        )
    except ValueError:
        return UnifiedToolOutput.failure(
            message="Call history cursor unavailable; restart at the first page.",
            error_code="INVALID_INPUT",
        )
    return UnifiedToolOutput.data_success(
        message="Retained owned calls with observed recorded platform consumption. Follow next_cursor. Missing usage is unavailable, not proof of zero cost; purged associations may omit delegated runs, and this is not a vendor invoice.",
        structured_data=result.model_dump(mode="json"),
        metadata={"application_phone_call_cursor": True},
    )
