"""Real tool, durable command, HITL dispatcher, edit, replay and resource publication."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import func, select

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.effects.models import AgentEffect
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_space_tools
from src.domains.rag_spaces.models import RAGSpace
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit", "replay"])
async def test_space_tool_requires_exact_human_approval(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    owner = test_user.id

    @asynccontextmanager
    async def session():
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "space_create_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr(application_space_tools, "get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    queue = asyncio.Queue()
    with installed_runtime_context(user_id=owner, deps=object(), side_channel_queue=queue):
        proposal = await application_space_tools.create_lia_knowledge_space_tool.coroutine(
            request={"name": "Confirmed space", "description": "Literal purpose"},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert (
            proposal.success and proposal.metadata["requires_confirmation"]
        ), proposal.model_dump()
        assert await async_session.scalar(select(func.count(RAGSpace.id))) == 0
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        if scenario == "no_confirmation":
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
            return
        if scenario == "edit":
            original = draft.command_id
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(
                    draft.model_dump(mode="json"),
                    {"intent": {"name": "Edited space", "description": "Edited purpose"}},
                )
            )
            assert draft.command_id == original
        with patch.dict(draft_executor.EXECUTOR_REGISTRY):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            invocation = {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": draft.model_dump(mode="json"),
            }
            result = await draft_executor._execute_confirmed_draft(
                invocation,
                {"configurable": {"thread_id": "space-create-flow"}},
                "space-create-flow",
                "fr",
            )
            assert result.success, result.to_agent_result()
            if scenario == "replay":
                replay = await draft_executor._execute_confirmed_draft(
                    invocation,
                    {"configurable": {"thread_id": "space-create-flow"}},
                    "space-create-flow",
                    "fr",
                )
                assert replay.success and replay.result_data == result.result_data
        assert await async_session.scalar(select(func.count(RAGSpace.id))) == 1
        assert (
            await async_session.scalar(
                select(func.count(AgentEffect.id)).where(AgentEffect.user_id == owner)
            )
            == 1
        )
        actual = await async_session.get(RAGSpace, draft.command_id)
        assert actual.name == ("Edited space" if scenario == "edit" else "Confirmed space")
        events = [queue.get_nowait() for _ in range(queue.qsize())]
        changes = [event for event in events if event.type == "application_state_changed"]
        assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == ["spaces"]
