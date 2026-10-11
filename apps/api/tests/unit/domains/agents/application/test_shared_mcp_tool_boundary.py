"""A personal shared MCP change remains a durable confirmation, never an immediate write."""

from contextlib import asynccontextmanager
from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.users.models import User
from src.infrastructure.mcp.preferences_contract import SharedMCPPreferenceSnapshot
from src.infrastructure.mcp.preferences_gateway import (
    SharedMCPPreferencesGateway,
    configure_shared_mcp_preferences,
)
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit


async def test_native_raw_change_persists_confirmation_without_changing_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = import_module("src.domains.agents.tools.application_shared_mcp_tools")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "mcp_enabled", True)
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    snapshot = SharedMCPPreferenceSnapshot(
        server_key="shared",
        name="Shared",
        enabled_for_user=True,
        tools_count=1,
        catalogue_digest="a" * 64,
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, None, actor]
    writer = AsyncMock()
    previous = configure_shared_mcp_preferences(
        SharedMCPPreferencesGateway(AsyncMock(return_value=[snapshot]), writer)
    )

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(tools, "get_db_context", session)
    persist = AsyncMock()
    monkeypatch.setattr(tools, "save_command", persist)
    try:
        result = await tools.update_lia_shared_mcp_preferences_tool.coroutine(
            change={"server_key": "shared", "enabled": False},
            runtime=make_tool_runtime(user_id=actor.id, store=InMemoryStore()),
        )
    finally:
        configure_shared_mcp_preferences(previous)
    assert result.success and result.metadata["requires_confirmation"]
    writer.assert_not_awaited()
    persist.assert_awaited_once()
    assert persist.await_args.args[1].actor_id == actor.id
    db.commit.assert_not_awaited()


def test_public_schema_does_not_offer_global_mcp_configuration() -> None:
    tools = import_module("src.domains.agents.tools.application_shared_mcp_tools")
    schema = tools.update_lia_shared_mcp_preferences_tool.tool_call_schema
    assert set(schema.model_fields) == {"change"}
    assert set(schema.model_fields["change"].annotation.model_fields) == {"server_key", "enabled"}
