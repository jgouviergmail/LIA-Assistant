"""The assistant marks e-mails read or unread, on any mail provider (ADR-369, D2).

The clients gained one ``mark_read`` contract for the « Tools » section (Gmail's
``UNREAD`` label, Graph's ``isRead``, IMAP's ``\\Seen``); the owner decided that
what the clients gain reaches the assistant in the same lot. One neutral tool,
the active provider resolved by category. It acts without a card: a read state
is undone by the same call with the other boolean (REASON_UNDONE_BY_ONE_CALL).

A selection longer than the published bound is served up to it and the rest is
stated (``more_remaining``), never dropped; a message gone since it was listed
is named, and the rest of the selection is still changed.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.constants import EMAIL_READ_STATE_MAX_MESSAGES
from src.domains.agents.constants import AGENT_EMAIL, CONTEXT_DOMAIN_EMAILS
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.context.schemas import ContextSaveMode
from src.domains.agents.emails.read_state_manifest import (
    READ_STATE_IDS_DESCRIPTION,
    READ_STATE_READ_DESCRIPTION,
)
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.mailbox_draft_base import refusal
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.mail_read_state import READ_STATE_NOT_FOUND, unique_ids
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)


class SetEmailReadStateTool(ToolOutputMixin, ConnectorTool[GoogleGmailClient]):
    """Mark messages of the active mailbox read or unread."""

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    functional_category = "email"
    registry_enabled = True

    def __init__(self) -> None:
        """Initialise the read-state tool."""
        super().__init__(tool_name="set_email_read_state_tool", operation="mark_read")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Change the read state of the named messages, up to the published bound."""
        ids = unique_ids(str(message_id) for message_id in kwargs.get("message_ids") or [])
        if not ids:
            return refusal(
                ToolErrorCode.INVALID_INPUT,
                "message_ids is required: name the messages (from get_emails_tool or CONTEXT).",
            )
        read = bool(kwargs.get("read", True))
        served = ids[:EMAIL_READ_STATE_MAX_MESSAGES]
        result = await client.mark_read(served, read)
        logger.info(
            "email_read_state_set",
            user_id=str(user_id),
            read=read,
            updated=len(result["updated"]),
            failed=len(result["failed"]),
        )
        return {
            "updated": result["updated"],
            "failed": result["failed"],
            "read": read,
            "more_remaining": len(ids) > len(served),
            "not_attempted": ids[len(served) :],
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """What became of each message; a call that changed none of them fails."""
        if "error_code" in result:
            return UnifiedToolOutput.failure(
                message=str(result["message"]), error_code=str(result["error_code"])
            )
        updated, failed = result["updated"], result["failed"]
        if failed and not updated:
            gone = all(item["status"] == READ_STATE_NOT_FOUND for item in failed)
            return UnifiedToolOutput.failure(
                message=(
                    "None of these messages is in the mailbox any more: list them again."
                    if gone
                    else "The mailbox changed the read state of none of these messages."
                ),
                error_code=(
                    ToolErrorCode.NOT_FOUND.value
                    if gone
                    else ToolErrorCode.EXTERNAL_API_ERROR.value
                ),
            )
        state = "read" if result["read"] else "unread"
        message = f"[email] {len(updated)} marked {state}, {len(failed)} not"
        if result.get("not_attempted"):
            # The cut is stated where the model reads first, the ids in the data.
            message += (
                f"; {len(result['not_attempted'])} not attempted"
                f" (at most {EMAIL_READ_STATE_MAX_MESSAGES} per call): call again with them"
            )
        output = UnifiedToolOutput.action_success(message=message, structured_data=result)
        output.context_save_mode = ContextSaveMode.NONE
        return output


_set_email_read_state_tool_instance = SetEmailReadStateTool()


@connector_tool(
    name="set_email_read_state",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    context_save_mode=ContextSaveMode.NONE,
    category="write",
)
async def set_email_read_state_tool(
    message_ids: Annotated[list[str], READ_STATE_IDS_DESCRIPTION],
    read: Annotated[bool, READ_STATE_READ_DESCRIPTION],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Mark e-mails of the person's mailbox as read or unread, on any provider.

    Args:
        message_ids: The messages' ids.
        read: True marks them read, false unread.
        runtime: Tool runtime (injected).

    Returns:
        UnifiedToolOutput saying what became of each message.
    """
    return await _set_email_read_state_tool_instance.execute(
        runtime=runtime, message_ids=message_ids, read=read
    )


__all__ = ["SetEmailReadStateTool", "set_email_read_state_tool"]
