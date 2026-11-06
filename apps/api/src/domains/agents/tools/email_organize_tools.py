"""The assistant sorts e-mails and folders, on any mail provider (ADR-369, lot 4, D2).

The clients gained one contract for the « Tools » section (``mail_moves``); the owner
decided that what the clients gain reaches the assistant in the same lot. Two neutral
tools, the active provider resolved by category. Neither asks a card: each act is
undone by one more call (REASON_UNDONE_BY_ONE_CALL), and neither deletes a message for
good, which stays by the person's own hand (A2). A folder holding anything is refused,
so a folder this tool deletes held nothing to lose.

A move changes an id on Outlook and iCloud: what each message is called from now on
is returned, or the way back would name messages that left. A selection longer than
the published bound is served up to it and the rest is stated, never dropped.
"""

from __future__ import annotations

from typing import Annotated, Any, Final, cast
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.constants import EMAIL_ORGANIZE_MAX_MESSAGES
from src.core.exceptions import ConnectorAPIError
from src.domains.agents.constants import AGENT_EMAIL, CONTEXT_DOMAIN_EMAILS
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.context.schemas import ContextSaveMode
from src.domains.agents.emails.organize_manifest import (
    MAIL_FOLDER_ACTION_DESCRIPTION,
    MAIL_FOLDER_ACTIONS,
    MAIL_FOLDER_FOLDER_DESCRIPTION,
    MAIL_FOLDER_NAME_DESCRIPTION,
    ORGANIZE_ACTION_DESCRIPTION,
    ORGANIZE_ACTIONS,
    ORGANIZE_FOLDER_DESCRIPTION,
    ORGANIZE_IDS_DESCRIPTION,
)
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.mailbox_draft_base import (
    MAIL_SEARCH_REFUSALS,
    MAILBOX_REFUSALS,
    refusal,
    refusal_for,
)
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.mail_folders import (
    MailFolderNameTakenError,
    MailFolderNotEmptyError,
    SystemFolderError,
)
from src.domains.connectors.clients.mail_moves import MailPlace
from src.domains.connectors.clients.mail_read_state import READ_STATE_NOT_FOUND, unique_ids
from src.domains.connectors.clients.protocols import MailFolderClientProtocol
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)

#: Where each act sends a message, and where it leaves from when that matters.
_PLACES: Final[dict[str, tuple[MailPlace, MailPlace | None]]] = {
    "archive": (MailPlace(role="archive"), None),
    "spam": (MailPlace(role="spam"), None),
    "not_spam": (MailPlace(role="inbox"), MailPlace(role="spam")),
    "restore": (MailPlace(role="inbox"), MailPlace(role="trash")),
}
_STARS: Final[dict[str, bool]] = {"star": True, "unstar": False}
_HTTP_CONFLICT: Final = 409


class OrganizeEmailsTool(ToolOutputMixin, ConnectorTool[GoogleGmailClient]):
    """Sort messages of the active mailbox."""

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    functional_category = "email"
    registry_enabled = True

    def __init__(self) -> None:
        """Initialise the sorting tool."""
        super().__init__(tool_name="organize_emails_tool", operation="organize")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Do one act on the named messages, up to the published bound."""
        ids = unique_ids(str(message_id) for message_id in kwargs.get("message_ids") or [])
        action = str(kwargs.get("action") or "")
        folder = str(kwargs.get("folder") or "").strip()
        if not ids:
            return refusal(
                ToolErrorCode.INVALID_INPUT,
                "message_ids is required: name the messages (from get_emails_tool or CONTEXT).",
            )
        if action not in ORGANIZE_ACTIONS:
            return refusal(ToolErrorCode.INVALID_INPUT, f"action is one of {ORGANIZE_ACTIONS}.")
        if action == "move" and not folder:
            return refusal(ToolErrorCode.INVALID_INPUT, "A move needs `folder`: name it.")
        served = ids[:EMAIL_ORGANIZE_MAX_MESSAGES]
        try:
            result = await _act(client, action, served, folder)
        except (*MAIL_SEARCH_REFUSALS, *MAILBOX_REFUSALS) as error:
            return refusal_for(error)
        logger.info(
            "emails_organized",
            user_id=str(user_id),
            action=action,
            updated=len(result["updated"]),
            failed=len(result["failed"]),
        )
        return {
            "action": action,
            "updated": result["updated"],
            "failed": result["failed"],
            "moved": result.get("moved") or {},
            "more_remaining": len(ids) > len(served),
            "not_attempted": ids[len(served) :],
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """What became of each message; a call that did none of them fails."""
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
                    else "The mailbox did this to none of these messages."
                ),
                error_code=(
                    ToolErrorCode.NOT_FOUND.value
                    if gone
                    else ToolErrorCode.EXTERNAL_API_ERROR.value
                ),
            )
        message = f"[email] {result['action']}: {len(updated)} done, {len(failed)} not"
        if result.get("not_attempted"):
            # The cut is stated where the model reads first, the ids in the data.
            message += (
                f"; {len(result['not_attempted'])} not attempted"
                f" (at most {EMAIL_ORGANIZE_MAX_MESSAGES} per call): call again with them"
            )
        output = UnifiedToolOutput.action_success(message=message, structured_data=result)
        output.context_save_mode = ContextSaveMode.NONE
        return output


class ManageMailFolderTool(ToolOutputMixin, ConnectorTool[GoogleGmailClient]):
    """Create, rename or delete a folder of the person's own on Outlook or iCloud."""

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    functional_category = "email"
    registry_enabled = True

    def __init__(self) -> None:
        """Initialise the folder tool."""
        super().__init__(tool_name="manage_mail_folder_tool", operation="manage_folder")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Do one act on a folder of the person's own."""
        action = str(kwargs.get("action") or "")
        folder = str(kwargs.get("folder") or "").strip()
        name = str(kwargs.get("name") or "").strip()
        problem = _folder_request_problem(action, folder, name)
        if problem:
            return refusal(ToolErrorCode.INVALID_INPUT, problem)
        if isinstance(client, GoogleGmailClient):
            return refusal(
                ToolErrorCode.CONSTRAINT_VIOLATION,
                "Gmail has labels, no folders: use create_label_tool, update_label_tool or "
                "delete_label_tool.",
            )
        try:
            now = await _folder_act(cast(MailFolderClientProtocol, client), action, folder, name)
        except MailFolderNotEmptyError:
            return refusal(
                ToolErrorCode.CONSTRAINT_VIOLATION,
                "This folder holds messages or folders: it was not deleted. Move them first.",
            )
        except SystemFolderError:
            return refusal(
                ToolErrorCode.CONSTRAINT_VIOLATION,
                "This folder belongs to the mailbox: it can be neither renamed nor deleted.",
            )
        except MailFolderNameTakenError:
            return _name_taken()
        except ConnectorAPIError as error:
            if error.upstream_status_code == _HTTP_CONFLICT:
                return _name_taken()
            return refusal_for(error)
        except (*MAIL_SEARCH_REFUSALS, *MAILBOX_REFUSALS) as error:
            return refusal_for(error)
        logger.info("mail_folder_managed", user_id=str(user_id), action=action)
        return {"action": action, "folder": now}

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """What the folder is called now; a refusal is said."""
        if "error_code" in result:
            return UnifiedToolOutput.failure(
                message=str(result["message"]), error_code=str(result["error_code"])
            )
        output = UnifiedToolOutput.action_success(
            message=f"[email] folder: {result['action']} done", structured_data=result
        )
        output.context_save_mode = ContextSaveMode.NONE
        return output


async def _act(
    client: GoogleGmailClient, action: str, ids: list[str], folder: str
) -> dict[str, Any]:
    """One act on a selection, through the clients' one contract."""
    if action in _STARS:
        return await client.set_starred(ids, _STARS[action])
    if action == "move":
        return await client.move_emails(ids, await client.place_named(folder), None)
    place, origin = _PLACES[action]
    return await client.move_emails(ids, place, origin)


async def _folder_act(client: MailFolderClientProtocol, action: str, folder: str, name: str) -> str:
    """One act on a folder; what it is called from now on."""
    if action == "create":
        return await client.create_folder(name)
    if action == "rename":
        return await client.rename_folder(folder, name)
    await client.delete_folder(folder)
    return folder


def _folder_request_problem(action: str, folder: str, name: str) -> str | None:
    """What a folder request lacks; None when it can be acted on."""
    if action not in MAIL_FOLDER_ACTIONS:
        return f"action is one of {MAIL_FOLDER_ACTIONS}."
    if action in ("rename", "delete") and not folder:
        return "`folder` is required: name the folder."
    if action in ("create", "rename") and not name:
        return "`name` is required."
    if action == "rename" and "/" in name:
        return "A rename gives a folder a new own name, never a path."
    return None


def _name_taken() -> dict[str, Any]:
    return refusal(ToolErrorCode.CONFLICT, "A folder already has this name: nothing was changed.")


_organize_emails_tool_instance = OrganizeEmailsTool()
_manage_mail_folder_tool_instance = ManageMailFolderTool()


@connector_tool(
    name="organize_emails",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    context_save_mode=ContextSaveMode.NONE,
    category="write",
)
async def organize_emails_tool(
    action: Annotated[str, ORGANIZE_ACTION_DESCRIPTION],
    message_ids: Annotated[list[str], ORGANIZE_IDS_DESCRIPTION],
    folder: Annotated[str | None, ORGANIZE_FOLDER_DESCRIPTION] = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Sort e-mails of the person's mailbox, on any provider.

    Args:
        action: What to do to them.
        message_ids: The messages' ids.
        folder: For a move, the folder.
        runtime: Tool runtime (injected).

    Returns:
        UnifiedToolOutput saying what became of each message.
    """
    return await _organize_emails_tool_instance.execute(
        runtime=runtime, action=action, message_ids=message_ids, folder=folder
    )


@connector_tool(
    name="manage_mail_folder",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    context_save_mode=ContextSaveMode.NONE,
    category="write",
)
async def manage_mail_folder_tool(
    action: Annotated[str, MAIL_FOLDER_ACTION_DESCRIPTION],
    folder: Annotated[str | None, MAIL_FOLDER_FOLDER_DESCRIPTION] = None,
    name: Annotated[str | None, MAIL_FOLDER_NAME_DESCRIPTION] = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Create, rename or delete a folder of the person's own on Outlook or iCloud.

    Args:
        action: What to do.
        folder: The folder.
        name: Its new name.
        runtime: Tool runtime (injected).

    Returns:
        UnifiedToolOutput saying what the folder is called now.
    """
    return await _manage_mail_folder_tool_instance.execute(
        runtime=runtime, action=action, folder=folder, name=name
    )


__all__ = [
    "ManageMailFolderTool",
    "OrganizeEmailsTool",
    "manage_mail_folder_tool",
    "organize_emails_tool",
]
