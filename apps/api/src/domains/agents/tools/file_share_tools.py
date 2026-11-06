"""The assistant shares a file, on any drive (ADR-369, lot 6, D2).

What the clients gained for the « Tools » section reaches the assistant in the same lot. Sharing
tells a third party, so this tool only drafts it: the card is the confirmation, in both execution
modes, and ``execute_file_share_draft`` gives the access. It reads the file first, for the card
to name what is shared. Taking an access back and opening a link anyone can follow stay the
person's own gestures: the first is a card of its own to come, the second reaches nobody named.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import status
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import EmailStr, TypeAdapter, ValidationError

from src.core.exceptions import ConnectorAPIError
from src.domains.agents.constants import AGENT_FILE, CONTEXT_DOMAIN_FILES
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.context.schemas import ContextSaveMode
from src.domains.agents.drafts import FileShareDraftInput, create_file_share_draft
from src.domains.agents.drive.share_manifest import (
    FILE_SHARE_ROLES,
    SHARE_EMAIL_DESCRIPTION,
    SHARE_FILE_ID_DESCRIPTION,
    SHARE_ROLE_DESCRIPTION,
)
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.mailbox_draft_base import refusal
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)

_ADDRESS = TypeAdapter(EmailStr)
_DEFAULT_ROLE = "reader"


def _request_problem(file_id: str, email: str, role: str) -> str | None:
    """What a request lacks; None when it can be drafted."""
    if not file_id:
        return "`file_id` is required: name the item."
    try:
        _ADDRESS.validate_python(email)
    except ValidationError:
        return "`email` is required: a readable address."
    if role not in FILE_SHARE_ROLES:
        return f"role is one of {FILE_SHARE_ROLES}."
    return None


class ShareFileTool(ToolOutputMixin, ConnectorTool[GoogleDriveClient]):
    """Share an item of the active drive with someone, once the card is confirmed."""

    connector_type = ConnectorType.GOOGLE_DRIVE
    client_class = GoogleDriveClient
    functional_category = "files"
    registry_enabled = True

    def __init__(self) -> None:
        """Initialise the tool."""
        super().__init__(tool_name="share_file_tool", operation="share")

    async def execute_api_call(
        self,
        client: GoogleDriveClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Read the item and prepare its sharing for the card."""
        file_id = str(kwargs.get("file_id") or "").strip()
        email = str(kwargs.get("email") or "").strip()
        role = str(kwargs.get("role") or _DEFAULT_ROLE)
        problem = _request_problem(file_id, email, role)
        if problem:
            return refusal(ToolErrorCode.INVALID_INPUT, problem)
        try:
            item = await client.get_file_metadata(file_id, fields=["id", "name"])
        except ConnectorAPIError as error:
            if error.upstream_status_code == status.HTTP_404_NOT_FOUND:
                return refusal(ToolErrorCode.NOT_FOUND, "That item is not on the drive any more.")
            raise
        logger.info("file_share_drafted", user_id=str(user_id))
        return {"file_id": file_id, "email": email, "role": role, "name": item.get("name")}

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """The card that asks; a refusal is said."""
        if "error_code" in result:
            return UnifiedToolOutput.failure(
                message=str(result["message"]), error_code=str(result["error_code"])
            )
        return create_file_share_draft(
            FileShareDraftInput(**result, user_language=self.get_user_language())
        )


async def execute_file_share_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """Give the access the person confirmed; the drive tells them.

    Args:
        draft_content: The card's content.
        user_id: The draft's owner.
        deps: ToolDependencies for getting the client.

    Returns:
        The item shared.

    Raises:
        ValueError: The card holds no role a drive knows: nothing leaves.
    """
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    role = draft_content.get("role")
    if role not in FILE_SHARE_ROLES:
        raise ValueError("The card holds no role a drive knows.")
    client, _resolved_type = await resolve_client_for_category("files", user_id, deps)
    file_id = str(draft_content["file_id"])
    await client.share_with(file_id, str(draft_content["email"]), role)
    logger.info("file_share_draft_executed", user_id=str(user_id))
    return {"success": True, "file_id": file_id}


_share_file_tool_instance = ShareFileTool()


@connector_tool(
    name="share_file",
    agent_name=AGENT_FILE,
    context_domain=CONTEXT_DOMAIN_FILES,
    context_save_mode=ContextSaveMode.NONE,
    category="write",
)
async def share_file_tool(
    file_id: Annotated[str, SHARE_FILE_ID_DESCRIPTION],
    email: Annotated[str, SHARE_EMAIL_DESCRIPTION],
    role: Annotated[str, SHARE_ROLE_DESCRIPTION] = _DEFAULT_ROLE,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Share a file or a folder with someone, once the person confirms.

    Args:
        file_id: The item.
        email: Who it is shared with.
        role: What they may do.
        runtime: Tool runtime (injected).

    Returns:
        UnifiedToolOutput with the card, or what stopped it.
    """
    return await _share_file_tool_instance.execute(
        runtime=runtime, file_id=file_id, email=email, role=role
    )


__all__ = ["ShareFileTool", "execute_file_share_draft", "share_file_tool"]
