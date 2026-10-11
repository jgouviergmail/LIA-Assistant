"""Both modes prepare only; the original human-confirmed executor records one group change."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_plugin_tools
from src.domains.plugins.models import UserPlugin
from src.domains.skills.cache import SkillsCache
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime
from tests.integration.test_application_plugin_read import _plugin

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize("confirmed", [False, True])
async def test_original_plugin_confirmation_and_owned_group_refresh(
    async_session, test_user, monkeypatch, tmp_path, mode, confirmed
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "plugins_enabled", True)
    monkeypatch.setattr(settings, "plugins_users_path", str(tmp_path))
    monkeypatch.setattr(SkillsCache, "invalidate_and_reload", AsyncMock())
    owner = test_user.id
    plugin = await _plugin(async_session, owner, "confirmed-plugin")
    identity = plugin.id
    await async_session.commit()

    @asynccontextmanager
    async def database():
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", database)
    monkeypatch.setattr(application_plugin_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    events = asyncio.Queue()
    with installed_runtime_context(
        user_id=owner, deps=object(), execution_mode=mode, side_channel_queue=events
    ):
        proposal = await application_plugin_tools.delete_lia_plugin_tool.coroutine(
            request={"plugin_id": identity},
            runtime=make_tool_runtime(
                user_id=owner, store=InMemoryStore(), execution_mode=mode, side_channel_queue=events
            ),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        assert (
            await async_session.scalar(select(UserPlugin.id).where(UserPlugin.id == identity))
            == identity
        )
        if confirmed:
            with patch.dict(draft_executor.EXECUTOR_REGISTRY):
                draft_executor.register_executor(
                    "application_action", execute_application_action_draft
                )
                result = await draft_executor._execute_confirmed_draft(
                    {
                        "draft_id": item.id,
                        "draft_type": "application_action",
                        "draft_content": draft.model_dump(mode="json"),
                    },
                    {"configurable": {"thread_id": "plugin-state-flow"}},
                    "plugin-state-flow",
                    "fr",
                )
            assert result.success and result.result_data["committed"]
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
        assert (
            await async_session.scalar(select(UserPlugin.id).where(UserPlugin.id == identity))
            is None
        ) == confirmed
        changes = []
        while not events.empty():
            event = events.get_nowait()
            if event.type == "application_state_changed":
                changes.append(event)
        assert len(changes) == int(confirmed)
        if confirmed:
            assert changes[0].metadata["change"]["resources"] == ["plugins", "skills", "user_mcp"]
            assert changes[0].metadata["change"]["changed_fields"] == ["plugin_to_delete"]
