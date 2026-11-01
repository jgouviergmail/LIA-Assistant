"""The MCP servers an account can call — what a routine may pre-approve (spec 2026-10-29 D9).

Two families, keyed the way a tool manifest names its server (``mcp_server_key``):
the account's OWN servers, enabled and active (their id), and the administrator's
servers it has not switched off (their key). The routine form offers exactly
these; its REST route accepts exactly these.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domains.user_mcp.repository import UserMCPServerRepository
from src.domains.user_mcp.shared_preference_commands import list_shared_server_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domains.users.models import User


async def callable_mcp_servers(db: AsyncSession, user: User) -> dict[str, str]:
    """Every MCP server the account can call now, by key, with its display name.

    Args:
        db: The request's session.
        user: The account (its switched-off administrator servers are read on it).

    Returns:
        ``{server_key: name}`` — personal servers by id, then the administrator's.
    """
    personal = await UserMCPServerRepository(db).get_enabled_active_for_user(user.id)
    shared = [server for server in list_shared_server_settings(user) if server.enabled_for_user]
    return {
        **{str(server.id): server.name for server in personal},
        **{server.server_key: server.name for server in shared},
    }
