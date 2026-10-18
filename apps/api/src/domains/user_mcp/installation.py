"""Server-only offline installation policy; never accepted from an HTTP payload."""

from dataclasses import dataclass
from uuid import UUID

from src.core.config import settings
from src.core.exceptions import ValidationError
from src.domains.user_mcp.models import UserMCPAuthType, UserMCPServerStatus
from src.domains.user_mcp.repository import UserMCPServerRepository
from src.infrastructure.mcp.security import validate_http_endpoint


async def check_creation_constraints(
    repository: UserMCPServerRepository, user_id: UUID, name: str
) -> None:
    """Native creation quota/name policy, shared by ordinary and offline imports."""
    maximum = settings.mcp_user_max_servers_per_user
    if await repository.count_for_user(user_id) >= maximum:
        raise ValidationError(f"Maximum of {maximum} MCP servers per user")
    if await repository.get_by_name_for_user(user_id, name):
        raise ValidationError(f"An MCP server named '{name}' already exists")


@dataclass(frozen=True)
class ValidatedMCPEndpoint:
    url: str


async def validate_install_endpoint(url: str) -> ValidatedMCPEndpoint:
    """Perform DNS/SSRF checks before opening the installation transaction."""
    valid, _ = await validate_http_endpoint(url)
    if not valid:
        raise ValidationError("Invalid MCP server endpoint")
    return ValidatedMCPEndpoint(url)


@dataclass(frozen=True)
class OfflineMCPInstallation:
    auth_type: UserMCPAuthType
    header_name: str | None = None
    endpoint: ValidatedMCPEndpoint | None = None
    oauth_scopes: str | None = None

    @property
    def credential_header(self) -> str | None:
        return self.header_name if self.auth_type is UserMCPAuthType.API_KEY else None

    @property
    def status(self) -> str:
        return str(
            (
                UserMCPServerStatus.INACTIVE
                if self.auth_type is UserMCPAuthType.NONE
                else UserMCPServerStatus.AUTH_REQUIRED
            ).value
        )
