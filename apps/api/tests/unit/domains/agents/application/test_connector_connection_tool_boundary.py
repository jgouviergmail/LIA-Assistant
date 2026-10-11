"""Connection-card tools cannot bypass the concrete local-unlink confirmation."""

from contextlib import asynccontextmanager
from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.users.models import User
from tests.helpers.runtime_context import make_tool_runtime
from tests.unit.domains.connectors.test_removal_commands import connector

pytestmark = pytest.mark.unit


async def test_native_selector_prepares_a_durable_confirmation_without_unlinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = import_module("src.domains.agents.tools.application_connection_tools")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    saved = connector(actor)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, actor, saved]

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(tools, "get_db_context", session)
    persist = AsyncMock()
    monkeypatch.setattr(tools, "save_command", persist)
    result = await tools.disconnect_lia_connector_tool.coroutine(
        change={"connector_id": str(saved.id)},
        runtime=make_tool_runtime(user_id=actor.id, store=InMemoryStore()),
    )
    assert result.success and result.metadata["requires_confirmation"]
    persist.assert_awaited_once()
    db.commit.assert_not_awaited()
    db.delete.assert_not_awaited()
    assert persist.await_args.args[1].actor_id == actor.id


def test_native_schema_never_offers_credentials_or_global_account_authority() -> None:
    tools = import_module("src.domains.agents.tools.application_connection_tools")
    schema = tools.disconnect_lia_connector_tool.tool_call_schema
    assert set(schema.model_fields) == {"change"}
    assert set(schema.model_fields["change"].annotation.model_fields) == {"connector_id"}


async def test_corrupt_saved_identity_is_not_reported_as_a_bad_user_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = import_module("src.domains.agents.tools.application_connection_tools")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    saved = connector(actor)
    saved.connector_metadata = {"oauth_account_email": ["invalid", "private-token"]}
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, actor, saved]

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(tools, "get_db_context", session)
    persist = AsyncMock()
    monkeypatch.setattr(tools, "save_command", persist)
    result = await tools.disconnect_lia_connector_tool.coroutine(
        change={"connector_id": str(saved.id)},
        runtime=make_tool_runtime(user_id=actor.id, store=InMemoryStore()),
    )
    assert result.error_code == "INVALID_RESPONSE_FORMAT"
    assert "private-token" not in str(result)
    persist.assert_not_awaited()
