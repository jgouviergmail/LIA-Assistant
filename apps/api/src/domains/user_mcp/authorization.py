"""Original OAuth initiation owner reused by UI and approved browser continuations."""

from collections.abc import Awaitable, Callable
from typing import TypedDict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import BaseAPIException, ValidationError, raise_bad_gateway
from src.domains.user_mcp.schemas import UserMCPOAuthInitiateResponse
from src.domains.user_mcp.service import UserMCPServerService
from src.infrastructure.mcp.oauth_application_guard import MCPApplicationOAuthCheck
from src.infrastructure.mcp.oauth_flow import MCPOAuthFlowHandler
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class _ApplicationArguments(TypedDict, total=False):
    application_command_id: UUID | None
    application_check: MCPApplicationOAuthCheck | None


def _application_arguments(
    command_id: UUID | None, check: MCPApplicationOAuthCheck | None
) -> _ApplicationArguments:
    if command_id is None:
        return {}
    return {"application_command_id": command_id, "application_check": check}


class _StoredOAuthClient(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)
    client_id: str | None = None
    client_secret: str | None = None
    issuer: str | None = None


async def initiate_personal_mcp_authorization(
    db: AsyncSession,
    user_id: UUID,
    server_id: UUID,
    *,
    before_flow: Callable[[AsyncSession], Awaitable[None]] | None = None,
    before_write: Callable[[AsyncSession], Awaitable[None]] | None = None,
    application_command_id: UUID | None = None,
    application_check: MCPApplicationOAuthCheck | None = None,
    metadata_sink: Callable[[dict[str, JsonValue]], Awaitable[None]] | None = None,
) -> UserMCPOAuthInitiateResponse:
    service = UserMCPServerService(db)
    server = await service.get_with_ownership_check(server_id, user_id)
    if server.auth_type != "oauth2":
        raise ValidationError("Server auth_type must be 'oauth2' to use OAuth authorization")
    try:
        client = _StoredOAuthClient.model_validate(service.get_decrypted_credentials(server) or {})
        cached: dict[str, JsonValue] | None = TypeAdapter(
            dict[str, JsonValue] | None
        ).validate_python(server.oauth_metadata)
        scopes: str | None = TypeAdapter(str | None).validate_python(
            (cached or {}).get("requested_scopes", ""), strict=True
        )
    except ValueError:
        raise ValidationError(
            "Stored OAuth configuration cannot be read; restore it in settings"
        ) from None
    endpoint = server.url
    if before_flow is not None:
        await before_flow(db)
    async with MCPOAuthFlowHandler() as handler:
        try:
            authorization_url, metadata_cache = await handler.initiate_flow(
                server_id=server_id,
                user_id=user_id,
                mcp_url=endpoint,
                cached_metadata=cached,
                client_id=client.client_id,
                client_secret=client.client_secret,
                requested_scopes=scopes,
                stored_issuer=client.issuer,
                **_application_arguments(application_command_id, application_check),
            )
        except BaseAPIException:
            raise
        except Exception as error:
            logger.error(
                "user_mcp_oauth_initiate_failed",
                user_id=str(user_id),
                server_id=str(server_id),
                error_type=type(error).__name__,
            )
            raise_bad_gateway(
                "Failed to initiate OAuth flow. The MCP server may be unreachable or misconfigured.",
                server_id=str(server_id),
            )
    if before_write is not None:
        await before_write(db)
    if metadata_cache and application_command_id is None:
        metadata = TypeAdapter(dict[str, JsonValue]).validate_python(metadata_cache)
        await service.cache_oauth_metadata(server, metadata)
        await db.commit()
    elif metadata_cache and metadata_sink is not None:
        await metadata_sink(TypeAdapter(dict[str, JsonValue]).validate_python(metadata_cache))
    return UserMCPOAuthInitiateResponse(authorization_url=authorization_url)
