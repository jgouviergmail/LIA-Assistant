"""The assistant's changes to MCP confirmation are judged here (spec 2026-10-30 D7).

From the chat, LIA can make itself ask more before an MCP tool, never less. Any
confirmation value but « always » is refused outright; every change is then judged by
the computation that alerts the person on the settings page (``questions_lost``), so
the chat never makes a change the page would warn about. The judge runs before a card
is proposed and again by the writer, under its row lock, against the state the write
replaces. The person's own page is not bound by it.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.domains.user_mcp.behavior import (
    BehaviorInputs,
    catalogue_tool,
    server_preview,
    strategy_preview,
)
from src.domains.user_mcp.behavior_schemas import BehaviorPreviewRequest
from src.domains.user_mcp.behavior_service import MCPBehaviorService
from src.domains.user_mcp.models import UserMCPServer
from src.infrastructure.mcp.confirmation import ToolChoice
from src.infrastructure.mcp.confirmation_loosening import ConfirmationLooseningRefused
from src.infrastructure.mcp.personal_settings_contract import PersonalMCPSettingsValues

#: The settings the synthesis reads; the others (name, description, timeout) are never judged.
_JUDGED = frozenset({"hitl_required", "iterative_mode", "react_expand_iterative"})


def judge_settings_patch(
    stored: BehaviorInputs, account_value: bool | None, patch: PersonalMCPSettingsValues
) -> None:
    """Refuse an assistant's patch that would make LIA ask less about one server.

    Args:
        stored: The server as stored, its tools' choices included.
        account_value: ``users.mcp_hitl_required`` as stored.
        patch: The assistant's patch.

    Raises:
        ConfirmationLooseningRefused: A confirmation value but « always », or a change
            the synthesis says would stop LIA asking before an act.
        ResourceNotFoundError: A tool the server's last catalogue does not list.
    """
    sent = patch.model_fields_set
    if "hitl_required" in sent and patch.hitl_required is not True:
        raise ConfirmationLooseningRefused()
    for name in patch.always_ask_tools or ():
        if catalogue_tool(stored, name) is None:
            raise ResourceNotFoundError("user_mcp_tool", str(stored.server_id))
    changed = {
        field: getattr(patch, field)
        for field in sent & _JUDGED
        if getattr(patch, field) != getattr(stored, field)
    }
    if not changed and not patch.always_ask_tools:
        return
    always: dict[str, ToolChoice | None] = dict.fromkeys(
        patch.always_ask_tools or (), ToolChoice.ALWAYS
    )
    request = BehaviorPreviewRequest(**changed, tool_choices=always)
    if server_preview(stored, account_value, request).questions_lost:
        raise ConfirmationLooseningRefused()


def judge_strategy(
    servers: Sequence[BehaviorInputs], stored: bool | None, candidate: bool | None
) -> None:
    """Refuse an assistant's change of the account's strategy that would make LIA ask less.

    Args:
        servers: Every server of the account as stored, its tools' choices included.
        stored: The account's strategy as stored.
        candidate: The strategy the assistant would write.

    Raises:
        ConfirmationLooseningRefused: A value but « always », or one that would stop LIA
            asking before an act on any server.
    """
    if candidate is not True:
        raise ConfirmationLooseningRefused()
    if strategy_preview(servers, stored, candidate).questions_lost:
        raise ConfirmationLooseningRefused()


async def refuse_settings_loosening(
    db: AsyncSession, row: UserMCPServer, patch: PersonalMCPSettingsValues
) -> None:
    """Judge an assistant's patch against the server as the session reads it now.

    Args:
        db: The session the write runs in (its row already locked by the writer).
        row: The person's server.
        patch: The assistant's patch.
    """
    behavior = MCPBehaviorService(db)
    judge_settings_patch(
        await behavior.inputs(row),
        await behavior.servers.repository.account_confirmation(row.user_id),
        patch,
    )


async def judge_personal_mcp_settings(
    db: AsyncSession, owner_id: UUID, server_id: UUID, patch: PersonalMCPSettingsValues
) -> None:
    """Refuse, before a card is proposed, a patch that would make LIA ask less.

    Args:
        db: A session.
        owner_id: The person.
        server_id: One of their servers.
        patch: The assistant's patch.
    """
    row = await MCPBehaviorService(db).servers.get_with_ownership_check(server_id, owner_id)
    await refuse_settings_loosening(db, row, patch)


async def judge_account_strategy(db: AsyncSession, owner_id: UUID, candidate: bool | None) -> None:
    """Refuse an assistant's change of the account's strategy that would make LIA ask less.

    Args:
        db: A session.
        owner_id: The person.
        candidate: The strategy the assistant would write.
    """
    if candidate is not True:
        raise ConfirmationLooseningRefused()
    behavior = MCPBehaviorService(db)
    judge_strategy(
        await behavior.account_inputs(owner_id),
        await behavior.servers.repository.account_confirmation(owner_id),
        candidate,
    )
