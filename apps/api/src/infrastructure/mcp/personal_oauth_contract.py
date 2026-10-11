"""Private OAuth URLs/tokens travel through typed owners, never tool results."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.infrastructure.mcp.oauth_application_guard import MCPApplicationOAuthCheck
from src.infrastructure.mcp.personal_state_contract import (
    PersonalMCPStateSnapshot,
    PersonalMCPWriteCheck,
)


class PersonalMCPOAuthStart(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    authorization_url: str
    metadata: dict[str, JsonValue]


class PersonalMCPOAuthStarter(Protocol):
    async def __call__(
        self,
        db: AsyncSession,
        user_id: UUID,
        server_id: UUID,
        *,
        application_command_id: UUID,
        application_check: MCPApplicationOAuthCheck,
    ) -> PersonalMCPOAuthStart: ...


class PersonalMCPOAuthWriter(Protocol):
    async def __call__(
        self,
        db: AsyncSession,
        owner_id: UUID,
        server_id: UUID,
        encrypted_credentials: str,
        metadata: dict[str, JsonValue],
        *,
        expected: PersonalMCPStateSnapshot,
        check: PersonalMCPWriteCheck,
    ) -> bool: ...


MCPApplicationOAuthStage = Callable[[UUID, UUID, UUID, str], Awaitable[None]]
MCPApplicationOAuthFail = Callable[[UUID], Awaitable[None]]


@dataclass(frozen=True)
class MCPApplicationOAuthCallbacks:
    check: MCPApplicationOAuthCheck
    stage: MCPApplicationOAuthStage
    fail: MCPApplicationOAuthFail


_callbacks: MCPApplicationOAuthCallbacks | None = None


def configure_application_mcp_oauth(
    callbacks: MCPApplicationOAuthCallbacks | None,
) -> MCPApplicationOAuthCallbacks | None:
    global _callbacks
    previous, _callbacks = _callbacks, callbacks
    return previous


def get_application_mcp_oauth() -> MCPApplicationOAuthCallbacks:
    if _callbacks is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _callbacks


async def check_application_mcp_oauth(server_id: UUID, user_id: UUID, command_id: UUID) -> None:
    await get_application_mcp_oauth().check(server_id, user_id, command_id)
