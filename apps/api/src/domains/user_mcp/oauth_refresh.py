"""A delayed refresh cannot overwrite a newer authorization or disconnected row."""

from uuid import UUID

from pydantic import JsonValue, TypeAdapter
from sqlalchemy import select

from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.user_mcp.models import UserMCPServer
from src.domains.user_mcp.oauth_credentials import persist_oauth_credentials
from src.domains.user_mcp.repository import UserMCPServerRepository
from src.infrastructure.database.session import get_db_context


async def persist_matching_oauth_refresh(
    server_id: UUID,
    owner_id: UUID,
    endpoint: str,
    url: str,
    expected: dict[str, JsonValue] | None,
    replacement: dict[str, JsonValue] | None,
) -> bool:
    """Own a short transaction; compare the actual token/configuration witness."""
    async with get_db_context() as db:
        row: UserMCPServer | None = await db.scalar(
            select(UserMCPServer)
            .where(
                UserMCPServer.id == server_id,
                UserMCPServer.user_id == owner_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None or row.auth_type != "oauth2" or row.status == "auth_required":
            return False
        if row.url != url or (row.oauth_metadata or {}).get("token_endpoint", "") != endpoint:
            return False
        try:
            actual = (
                TypeAdapter(dict[str, JsonValue]).validate_json(
                    decrypt_data(row.credentials_encrypted)
                )
                if row.credentials_encrypted
                else None
            )
        except ValueError:
            return False
        if actual != expected:
            return False
        repository = UserMCPServerRepository(db)
        if replacement is None:
            await repository.update(row, {"status": "auth_required"})
        else:
            payload = TypeAdapter(dict[str, JsonValue]).dump_json(replacement).decode("utf-8")
            await persist_oauth_credentials(repository, row, encrypt_data(payload))
        return True
