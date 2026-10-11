"""An already-bound shared MCP tool cannot bypass a newly saved account refusal."""

from contextlib import asynccontextmanager
from importlib import import_module
from inspect import unwrap
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.users.models import User
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def installed_access_policy():
    from src.domains.user_mcp.shared_access import require_shared_mcp_access
    from src.infrastructure.mcp.access_policy import configure_shared_mcp_access

    previous = configure_shared_mcp_access(require_shared_mcp_access)
    try:
        yield
    finally:
        configure_shared_mcp_access(previous)


@pytest.mark.parametrize("failure", ["disabled", "inactive", "deployment"])
async def test_fresh_shared_access_refuses_the_current_saved_or_platform_state(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    access = import_module("src.domains.user_mcp.shared_access")
    monkeypatch.setattr(settings, "mcp_enabled", failure != "deployment")
    actor = User(
        id=uuid4(),
        is_active=failure != "inactive",
        deleted_at=None,
        admin_mcp_disabled_servers=["shared"] if failure == "disabled" else [],
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, actor]

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(access, "get_db_context", session)
    with installed_runtime_context(user_id=actor.id), pytest.raises(AuthorizationError):
        await access.require_shared_mcp_access("shared", actor_id=actor.id)


async def test_previously_bound_adapter_refuses_before_a_cached_effect_is_replayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = import_module("src.domains.user_mcp.shared_access")
    effects = import_module("src.domains.agents.effects.runtime")
    monkeypatch.setattr(settings, "mcp_enabled", True)
    actor = User(id=uuid4(), is_active=True, deleted_at=None, admin_mcp_disabled_servers=["shared"])
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, actor]

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(access, "get_db_context", session)
    cached = AsyncMock(return_value={"success": True, "data": "previous private result"})
    monkeypatch.setattr(effects, "gated", lambda *_args: cached)
    adapter = MCPToolAdapter.from_mcp_tool(
        "shared", "read", "Read", {"type": "object", "properties": {}}
    )
    with installed_runtime_context(user_id=actor.id), pytest.raises(AuthorizationError):
        await adapter.coroutine()
    cached.assert_not_awaited()


@pytest.mark.parametrize("saved", [False, 0, {}, ""])
async def test_corrupt_empty_refusal_state_cannot_grant_access(
    monkeypatch: pytest.MonkeyPatch,
    saved: object,
) -> None:
    access = import_module("src.domains.user_mcp.shared_access")
    monkeypatch.setattr(settings, "mcp_enabled", True)
    actor = User(id=uuid4(), is_active=True, deleted_at=None, admin_mcp_disabled_servers=saved)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, actor]

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(access, "get_db_context", session)
    with pytest.raises(AuthorizationError) as refusal:
        await access.require_shared_mcp_access("shared", actor_id=actor.id)
    assert refusal.value.detail["error_code"] == "SERVICE_UNAVAILABLE"


async def test_disabled_iterative_server_is_refused_before_any_paid_model_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = import_module("src.domains.user_mcp.shared_access")
    tasks = import_module("src.domains.agents.tools.mcp_react_tools")
    monkeypatch.setattr(settings, "mcp_enabled", True)
    actor = User(id=uuid4(), is_active=True, deleted_at=None, admin_mcp_disabled_servers=["shared"])
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, actor]

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(access, "get_db_context", session)
    model = AsyncMock()
    monkeypatch.setattr(tasks, "_run_mcp_react_task", model)
    monkeypatch.setattr(tasks, "_get_mcp_server_tools_for_react", lambda _key: [object()])
    operation = unwrap(tasks.mcp_server_task_tool.coroutine)
    with installed_runtime_context(user_id=actor.id), pytest.raises(AuthorizationError):
        await operation(
            server_name="shared", task="Read facts", runtime=make_tool_runtime(user_id=actor.id)
        )
    model.assert_not_awaited()


async def test_failed_restart_withdraws_the_previous_access_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infrastructure.mcp.access_policy import (
        authorize_shared_mcp,
        configure_shared_mcp_access,
    )
    from src.infrastructure.mcp.preferences_gateway import (
        SharedMCPPreferencesGateway,
        configure_shared_mcp_preferences,
        get_shared_mcp_preferences,
    )
    from src.infrastructure.startup.integrations import init_mcp

    previous_policy = AsyncMock()
    old_read, old_write = AsyncMock(), AsyncMock()
    configure_shared_mcp_preferences(SharedMCPPreferencesGateway(old_read, old_write))
    configure_shared_mcp_access(previous_policy)
    monkeypatch.setattr(settings, "mcp_enabled", True)
    monkeypatch.setattr(
        "src.infrastructure.mcp.client_manager.initialize_mcp_client_manager",
        AsyncMock(side_effect=RuntimeError("unavailable")),
    )
    assert await init_mcp(AsyncMock()) is None
    with pytest.raises(AuthorizationError) as refusal:
        await authorize_shared_mcp("shared", actor_id=uuid4())
    assert refusal.value.detail["error_code"] == "SERVICE_UNAVAILABLE"
    previous_policy.assert_not_awaited()
    with pytest.raises(AuthorizationError):
        get_shared_mcp_preferences()
    old_read.assert_not_awaited()
    old_write.assert_not_awaited()
