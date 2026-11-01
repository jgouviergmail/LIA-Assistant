"""The display names of a routine's pre-approved MCP servers (spec 2026-10-29 D9).

Resolved when a command on the routine is prepared, for the card that names
them: the routines domain owns the stored pre-approval, and reaching the MCP
servers from here keeps the agents domain from importing them back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domains.shared.mcp_preapproval import stored_server_keys
from src.domains.user_mcp.callable_servers import callable_mcp_servers

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domains.scheduled_actions.models import ScheduledAction
    from src.domains.users.models import User


async def preapproval_names(db: AsyncSession, actor: User, row: ScheduledAction) -> tuple[str, ...]:
    """The display names of the servers a routine pre-approved, for its card.

    Args:
        db: The command's session.
        actor: The routine's owner.
        row: The routine.

    Returns:
        One name per stored key, in stored order — a server the account can no
        longer call keeps its key, so the card never hides a stale tick.
    """
    keys = stored_server_keys(row.mcp_preapproved_servers)
    if not keys:
        return ()
    names = await callable_mcp_servers(db, actor)
    return tuple(names.get(key, key) for key in keys)
