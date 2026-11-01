"""What a choice left open on the MCP servers page inherits (spec 2026-10-30 D2, D9).

The page shows, for every « default », what it currently gives; it never holds a copy
of an instance setting. Each value is read through its one reader
(``infrastructure/mcp/confirmation.py``).
"""

from __future__ import annotations

from src.domains.user_mcp.schemas import UserMCPDefaults
from src.infrastructure.mcp.confirmation import (
    dedicated_agents_available,
    effective_react_expand,
    instance_confirmation,
    resolve_server_confirmation,
)


def published_defaults(account_value: bool | None) -> UserMCPDefaults:
    """The defaults the page shows for one account.

    Args:
        account_value: ``users.mcp_hitl_required`` as stored (None: never chosen).

    Returns:
        The instance's and the account's confirmation, what « like my strategy »
        currently gives, the instance's ReAct shape and whether dedicated agents
        exist on this instance.
    """
    return UserMCPDefaults(
        confirmation_instance=instance_confirmation(),
        confirmation_account=account_value if isinstance(account_value, bool) else None,
        confirmation_effective=resolve_server_confirmation(None, account_value).always,
        react_direct_tools_default=effective_react_expand(None),
        dedicated_agents_available=dedicated_agents_available(),
    )
