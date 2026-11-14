"""What an OAuth consent was asked for, so its tokens land on that server or nowhere.

A consent takes minutes: the person approves at the authorization server while the row can
change in another tab (another type, address, client or requested scopes). Written then,
the tokens would overwrite the credentials of the type the server now uses and mark it
``active``, or bring back a grant issued for an address or scopes the server left behind.

The flow records the row's binding when it starts (``authorization_binding``) and the
callback stores the tokens only if the row still has it, under a lock on that row held by
the write itself (``persist_bound_oauth_credentials``), the way a token refresh conditions
its write (``oauth_refresh.persist_matching_oauth_refresh``).
"""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from sqlalchemy import select

from src.core.security.utils import decrypt_data
from src.domains.user_mcp.models import UserMCPAuthType, UserMCPServer
from src.domains.user_mcp.oauth_credentials import persist_oauth_credentials
from src.domains.user_mcp.repository import UserMCPServerRepository
from src.infrastructure.database.session import get_db_context


def authorization_binding(server: UserMCPServer, client_id: str | None) -> str:
    """The witness of the row a consent is asked for.

    Args:
        server: The server row the consent is for.
        client_id: The OAuth client stored for it when the consent starts, if any.

    Returns:
        A digest of its type, address, stored client and requested scopes.
    """
    scopes = (server.oauth_metadata or {}).get("requested_scopes") or None
    witness = [server.auth_type, server.url, client_id or None, scopes]
    return hashlib.sha256(json.dumps(witness).encode("utf-8")).hexdigest()


def stored_client_id(server: UserMCPServer) -> str | None:
    """The OAuth client stored in a row's credentials (``None`` when absent or unreadable).

    Args:
        server: The server row.

    Returns:
        The stored ``client_id``, or ``None``.
    """
    if not server.credentials_encrypted:
        return None
    try:
        blob = json.loads(decrypt_data(server.credentials_encrypted))
    except ValueError:
        return None
    client = blob.get("client_id") if isinstance(blob, dict) else None
    return client if isinstance(client, str) and client else None


async def persist_bound_oauth_credentials(
    server_id: UUID, owner_id: UUID, binding: str | None, encrypted_creds: str
) -> bool:
    """Store the tokens of a finished consent if the row is still the one it was asked for.

    Owns a short transaction and locks the row for the comparison and the write. A consent
    started before bindings were recorded (``binding`` is ``None``) is held to the type alone.

    Args:
        server_id: The server the consent was for.
        owner_id: The account that started it.
        binding: The row's ``authorization_binding`` when the consent started.
        encrypted_creds: The encrypted tokens and client the exchange produced.

    Returns:
        True when stored; False when the row is gone, is no longer OAuth or changed since.
    """
    async with get_db_context() as db:
        row: UserMCPServer | None = await db.scalar(
            select(UserMCPServer)
            .where(UserMCPServer.id == server_id, UserMCPServer.user_id == owner_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None or row.auth_type != UserMCPAuthType.OAUTH2.value:
            return False
        if binding is not None and authorization_binding(row, stored_client_id(row)) != binding:
            return False
        await persist_oauth_credentials(UserMCPServerRepository(db), row, encrypted_creds)
        return True
