"""Live preference tools prepare current-state confirmation without opening a session."""

from contextlib import asynccontextmanager
from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.live.preference_gateway import SavedLivePreferences
from src.domains.users.models import User
from src.infrastructure.live_preferences import configure_live_preferences
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit


async def test_live_change_only_creates_the_pending_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = import_module("src.domains.agents.tools.application_live_tools")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "live_enabled", True)
    actor = User(id=uuid4(), is_active=True, deleted_at=None, live_preferences=None)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, None, actor, actor]

    @asynccontextmanager
    async def session():
        yield db

    previous = configure_live_preferences(SavedLivePreferences())
    monkeypatch.setattr(tools, "get_db_context", session)
    persist = AsyncMock()
    monkeypatch.setattr(tools, "save_command", persist)
    try:
        result = await tools.update_lia_live_preferences_tool.coroutine(
            change={"end_of_speech": "calm"},
            runtime=make_tool_runtime(user_id=actor.id, store=InMemoryStore()),
        )
    finally:
        configure_live_preferences(previous)
    assert result.success and result.metadata["requires_confirmation"]
    persist.assert_awaited_once()
    db.commit.assert_not_awaited()
    assert actor.live_preferences is None


def test_live_schema_never_offers_a_key_session_provider_or_actor() -> None:
    tools = import_module("src.domains.agents.tools.application_live_tools")
    assert set(tools.update_lia_live_preferences_tool.tool_call_schema.model_fields) == {"change"}
    assert set(tools.get_lia_live_preferences_tool.tool_call_schema.model_fields) == set()


async def test_unreadable_saved_state_is_not_reported_as_an_invalid_user_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = import_module("src.domains.agents.tools.application_live_tools")
    db = AsyncMock(spec=AsyncSession)

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(tools, "get_db_context", session)
    monkeypatch.setattr(
        tools,
        "prepare_live_preference_content",
        AsyncMock(side_effect=ValueError("private-stored-data")),
    )
    result = await tools.update_lia_live_preferences_tool.coroutine(
        change={"end_of_speech": "calm"},
        runtime=make_tool_runtime(user_id=uuid4(), store=InMemoryStore()),
    )
    assert not result.success and result.error_code == "INVALID_RESPONSE_FORMAT"
    assert "private-stored-data" not in str(result)
