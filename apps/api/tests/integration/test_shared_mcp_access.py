"""A saved shared-server refusal takes effect on an already-bound RPC adapter."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.user_mcp import shared_preference_commands
from src.domains.user_mcp.shared_access import require_shared_mcp_access
from src.domains.users.models import User
from src.infrastructure.mcp.access_policy import authorize_shared_mcp, configure_shared_mcp_access
from src.infrastructure.mcp.schemas import MCPDiscoveredTool
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration


async def test_actual_toggle_denies_a_bound_adapter_before_any_cached_result(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "mcp_enabled", True)
    test_user.admin_mcp_disabled_servers = ["another-server"]
    await async_session.commit()
    actor_id = test_user.id
    manager = MagicMock()
    manager.discovered_tools = {
        "shared": [
            MCPDiscoveredTool(
                server_name="shared",
                tool_name="read",
                description="Facts",
                input_schema={"type": "object", "properties": {}},
            )
        ]
    }
    monkeypatch.setattr(
        shared_preference_commands.client_manager, "get_mcp_client_manager", lambda: manager
    )

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    cached = AsyncMock(return_value={"success": True, "data": "old private result"})
    previous = configure_shared_mcp_access(require_shared_mcp_access)
    try:
        with (
            patch("src.domains.user_mcp.shared_access.get_db_context", session),
            patch("src.domains.agents.effects.runtime.gated", lambda *_args: cached),
            installed_runtime_context(user_id=actor_id),
        ):
            adapter = MCPToolAdapter.from_mcp_tool(
                "shared", "read", "Read", {"type": "object", "properties": {}}
            )
            await authorize_shared_mcp("shared", actor_id=actor_id)
            before = shared_preference_commands.shared_mcp_snapshot(test_user, "shared")
            await shared_preference_commands.set_shared_mcp_enabled(
                async_session,
                actor_id,
                "shared",
                False,
                expected=before,
            )
            with pytest.raises(AuthorizationError) as refused:
                await adapter.coroutine()
            assert refused.value.detail["error_code"] == "MCP_SERVER_DISABLED"
            cached.assert_not_awaited()
            await async_session.refresh(test_user)
            assert test_user.admin_mcp_disabled_servers == ["another-server", "shared"]
            before = shared_preference_commands.shared_mcp_snapshot(test_user, "shared")
            await shared_preference_commands.set_shared_mcp_enabled(
                async_session,
                actor_id,
                "shared",
                True,
                expected=before,
            )
            assert (await adapter.coroutine())["success"] is True
            cached.assert_awaited_once()
    finally:
        configure_shared_mcp_access(previous)
