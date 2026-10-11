"""Native channel management is private, concrete and draft-only."""

from contextlib import asynccontextmanager
from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.channels.models import UserChannelBinding
from src.domains.users.models import User
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit


async def test_raw_channel_request_prepares_a_durable_snapshot_without_toggling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = import_module("src.domains.agents.tools.application_channel_tools")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "channels_enabled", True)
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    binding = UserChannelBinding(
        id=uuid4(),
        user_id=actor.id,
        channel_type="telegram",
        channel_user_id="private-id",
        channel_username="@reader",
        is_active=True,
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, None, actor, binding]

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(tools, "get_db_context", session)
    persist = AsyncMock()
    monkeypatch.setattr(tools, "save_command", persist)
    result = await tools.update_lia_channel_binding_tool.coroutine(
        change={"binding_id": str(binding.id), "enabled": False},
        runtime=make_tool_runtime(user_id=actor.id, store=InMemoryStore()),
    )
    assert result.success and result.metadata["requires_confirmation"]
    assert binding.is_active is True
    db.commit.assert_not_awaited()
    assert persist.await_count == 1
    content = persist.await_args.args[1]
    assert content.actor_id == actor.id and content.operation_id == "channel_binding.update"
    assert content.after["channel_binding"]["is_active"] is False


def test_the_model_can_select_a_binding_but_cannot_supply_its_identity_or_actor() -> None:
    tools = import_module("src.domains.agents.tools.application_channel_tools")
    offered = tools.update_lia_channel_binding_tool.tool_call_schema
    assert set(offered.model_fields) == {"change"}
    assert set(offered.model_fields["change"].annotation.model_fields) == {"binding_id", "enabled"}
