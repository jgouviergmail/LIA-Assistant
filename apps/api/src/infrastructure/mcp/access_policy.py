"""Injected account access policy for shared MCP consumers, bound by application startup."""

from typing import Protocol
from uuid import UUID

from src.core.exceptions import AuthorizationError


class SharedMCPAccessPolicy(Protocol):
    async def __call__(self, server_key: str, *, actor_id: UUID) -> None: ...


_policy: SharedMCPAccessPolicy | None = None


def configure_shared_mcp_access(
    policy: SharedMCPAccessPolicy | None,
) -> SharedMCPAccessPolicy | None:
    global _policy
    previous = _policy
    _policy = policy
    return previous


async def authorize_shared_mcp(server_key: str, *, actor_id: UUID | None) -> None:
    if actor_id is None:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    policy = _policy
    if policy is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    await policy(server_key, actor_id=actor_id)
