"""One SQL payload and public diagnostic for encrypted personal MCP OAuth credentials."""

from src.domains.user_mcp.models import UserMCPServer, UserMCPServerStatus
from src.domains.user_mcp.repository import UserMCPServerRepository
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


async def persist_oauth_credentials(
    repository: UserMCPServerRepository, server: UserMCPServer, encrypted_creds: str
) -> None:
    await repository.update(
        server,
        {
            "credentials_encrypted": encrypted_creds,
            "status": UserMCPServerStatus.ACTIVE.value,
        },
    )
    logger.info("user_mcp_oauth_credentials_updated", server_id=str(server.id))
