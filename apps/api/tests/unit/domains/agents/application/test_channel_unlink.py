"""An unlink is an exact destructive proposal, never an implicit disable or write."""

from contextlib import asynccontextmanager
from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.channels.models import UserChannelBinding
from src.domains.users.models import User
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit


async def test_unlink_freezes_owned_identity_and_shows_removal_before_any_write(
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
        channel_user_id="private-unlink-id",
        channel_username="@reader",
        is_active=False,
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, None, actor, binding]

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(tools, "get_db_context", session)
    persist = AsyncMock()
    monkeypatch.setattr(tools, "save_command", persist)
    result = await tools.unlink_lia_channel_binding_tool.coroutine(
        binding={"binding_id": str(binding.id)},
        runtime=make_tool_runtime(user_id=actor.id, store=InMemoryStore()),
    )
    assert result.success and result.metadata["requires_confirmation"]
    draft = persist.await_args.args[1]
    assert draft.operation_id == "channel_binding.unlink"
    assert draft.before["channel_binding"]["id"] == str(binding.id)
    assert draft.after == {"channel_binding": None}
    db.delete.assert_not_awaited()
    db.commit.assert_not_awaited()
    content = draft.model_dump(mode="json")
    lines = render_application_preview(
        content, get_draft_preview_labels("fr"), lambda value: value or ""
    )
    assert any("@reader" in str(line) and "null" in str(line) for line in lines)
    prompt = str(build_application_edit_prompt(content, "Retire plutôt ce canal"))
    assert "private-unlink-id" not in prompt and "channel_user_id" not in prompt
    assert "binding_id" in prompt and "enabled" not in prompt


def test_unlink_public_schema_never_offers_actor_or_private_binding_state() -> None:
    tools = import_module("src.domains.agents.tools.application_channel_tools")
    offered = tools.unlink_lia_channel_binding_tool.tool_call_schema
    assert set(offered.model_fields) == {"binding"}
    assert set(offered.model_fields["binding"].annotation.model_fields) == {"binding_id"}
