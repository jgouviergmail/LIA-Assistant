"""How a routine's MCP pre-approval can be refused (spec 2026-10-29 D9).

The refusal names itself with a stable code (``detail.code``) the web app
translates in the person's language, the refused keys beside it. Built on the
central taxonomy (rule #18: never a raw ``HTTPException``) and kept in the domain,
like the e-mail share's and the bookmarks' raisers, because ``core/exceptions.py``
is size-frozen.
"""

from __future__ import annotations

from typing import Final, NoReturn

from fastapi import status

from src.core.exceptions import BaseAPIException

#: A pre-approval names a server the account cannot call (another account's,
#: one switched off, or one that does not exist).
MCP_SERVER_NOT_CALLABLE: Final = "routine_mcp_server_not_callable"


def refuse_mcp_preapproval(servers: list[str]) -> NoReturn:
    """Refuse a pre-approval naming servers the account cannot call.

    Args:
        servers: The refused keys, in the order they were sent.

    Raises:
        BaseAPIException: 400 with ``detail = {"code": ..., "servers": [...]}``.
    """
    raise BaseAPIException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": MCP_SERVER_NOT_CALLABLE, "servers": servers},
        log_level="info",
        log_event="routine_mcp_preapproval_refused",
        refused_count=len(servers),
    )
