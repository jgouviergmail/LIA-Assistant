"""An old widget session cannot bypass a newly saved shared-server refusal."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.user_mcp import admin_router, shared_access
from src.domains.user_mcp.schemas import McpAppCallToolRequest, McpAppReadResourceRequest
from src.domains.users.models import User

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("read", [False, True])
async def test_widget_proxy_reads_fresh_refusal_before_any_rpc(
    monkeypatch: pytest.MonkeyPatch,
    read: bool,
) -> None:
    monkeypatch.setattr(settings, "mcp_enabled", True)
    actor_id = uuid4()
    stale = User(id=actor_id, is_active=True, deleted_at=None, admin_mcp_disabled_servers=[])
    current = User(
        id=actor_id, is_active=True, deleted_at=None, admin_mcp_disabled_servers=["shared"]
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, current]

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(shared_access, "get_db_context", session)
    manager = MagicMock()
    manager.discovered_tools = {"shared": []}
    manager.call_tool, manager.read_resource = AsyncMock(), AsyncMock()
    monkeypatch.setattr(
        "src.infrastructure.mcp.client_manager.get_mcp_client_manager", lambda: manager
    )
    with pytest.raises(AuthorizationError):
        if read:
            await admin_router.admin_app_proxy_read_resource(
                "shared", McpAppReadResourceRequest(uri="ui://widget"), stale
            )
        else:
            await admin_router.admin_app_proxy_call_tool(
                "shared", McpAppCallToolRequest(tool_name="read", arguments={}), stale
            )
    manager.call_tool.assert_not_awaited()
    manager.read_resource.assert_not_awaited()
