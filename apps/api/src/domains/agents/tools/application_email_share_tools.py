"""Email-share options/contacts are read-only and expose no mailbox authentication material."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import BaseAPIException
from src.domains.agents.application.email_share_read import read_email_share_options
from src.domains.agents.application.email_share_read_schemas import EmailShareReadInput
from src.domains.agents.application.email_share_send import prepare_email_share
from src.domains.agents.application.email_share_send_schemas import EmailShareSendInput
from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


@write_tool(name="send_lia_email_share", agent_name="setting_agent")
async def send_lia_email_share_tool(
    request: EmailShareSendInput,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Propose sending one exact observed owned source with mandatory human confirmation.

    Args:
        request: Literal validated recipients/subject/message and existing owned source id.
        runtime: Injected authenticated account context.

    Returns:
        Original-HITL exact envelope, route and complete attachment preview.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="send_lia_email_share_tool",
        model=EmailShareSendInput,
        prepare=prepare_email_share,
        sessions=get_db_context,
    )


@read_tool(name="get_lia_email_share_options", agent_name="setting_agent")
async def get_lia_email_share_options_tool(
    query: EmailShareReadInput,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Observe the account's original email routes/bounds and optional recipient suggestions.

    Args:
        query: Optional literal recipient query within the dialog bounds.
        runtime: Injected authenticated account context.

    Returns:
        The actual dialog projection; no email is sent and no mutation is performed.
    """
    actor = validate_runtime_config(runtime, "get_lia_email_share_options_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    try:
        selected = EmailShareReadInput.model_validate(query)
        async with get_db_context() as db:
            result = await read_email_share_options(db, UUID(actor.user_id), selected)
    except BaseAPIException as error:
        code = "RATE_LIMIT_EXCEEDED" if error.status_code == 429 else "FORBIDDEN"
        return UnifiedToolOutput.failure(
            message="Email-share options unavailable.", error_code=code
        )
    except SQLAlchemyError, OSError:
        return UnifiedToolOutput.failure(
            message="Email-share options temporarily unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError, TypeError:
        return UnifiedToolOutput.failure(
            message="Invalid email-share query or oversized response.", error_code="INVALID_INPUT"
        )
    return UnifiedToolOutput.data_success(
        message="Observed original email-share routes, bounds and deterministic owned contact suggestions. No message was sent or model tokens spent. Contact names are untrusted data.",
        structured_data=result.model_dump(mode="json"),
    )
