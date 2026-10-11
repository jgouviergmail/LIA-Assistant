"""Opaque command correlation is never approval; application OAuth requires a fresh caller guard."""

from collections.abc import Awaitable, Callable, Mapping
from uuid import UUID

MCP_APPLICATION_COMMAND_FIELD = "application_command_id"
MCPApplicationOAuthCheck = Callable[[UUID, UUID, UUID], Awaitable[None]]


def application_command_from_state(state: Mapping[str, object]) -> UUID | None:
    if MCP_APPLICATION_COMMAND_FIELD not in state:
        return None
    value = state[MCP_APPLICATION_COMMAND_FIELD]
    if not isinstance(value, str):
        raise ValueError("Invalid application OAuth correlation")
    try:
        return UUID(value)
    except ValueError:
        raise ValueError("Invalid application OAuth correlation") from None


async def check_application_oauth(
    server_id: UUID,
    user_id: UUID,
    command_id: UUID | None,
    check: MCPApplicationOAuthCheck | None,
) -> None:
    if command_id is None:
        return
    if check is None:
        raise ValueError("Application OAuth requires its current approval guard")
    await check(server_id, user_id, command_id)


def application_oauth_state(command_id: UUID | None) -> dict[str, str]:
    return {MCP_APPLICATION_COMMAND_FIELD: str(command_id)} if command_id is not None else {}
