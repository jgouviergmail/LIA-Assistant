"""Confirmed space edits use the actual native dispatcher, effect journal and refresh event."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import uuid4

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
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit", "retarget", "replay"])
async def test_space_update_exact_confirmation_flow(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Original personal space")
    async_session.add(space)
    await async_session.commit()
    identity = space.id

    @asynccontextmanager
    async def session():
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "space_update_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr(application_space_tools, "get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    queue = asyncio.Queue()
    with installed_runtime_context(user_id=owner, deps=object(), side_channel_queue=queue):
        proposal = await application_space_tools.update_lia_knowledge_space_tool.coroutine(
            request={"space_id": identity, "name": "Confirmed rename", "is_active": False},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert (
            proposal.success and proposal.metadata["requires_confirmation"]
        ), proposal.model_dump()
        actual = await async_session.get(RAGSpace, identity, populate_existing=True)
        assert actual.name == "Original personal space" and actual.is_active
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        if scenario == "no_confirmation":
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
            return
        if scenario in {"edit", "retarget"}:
            modified = {
                "intent": {
                    "space_id": str(identity),
                    "description": "Edited purpose",
                    "is_active": False,
                }
            }
            if scenario == "retarget":
                modified["intent"]["space_id"] = str(uuid4())
                with pytest.raises(CommandRejected, match="INVALID_INPUT"):
                    await rebuild_application_draft(draft.model_dump(mode="json"), modified)
                return
            original_command = draft.command_id
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(draft.model_dump(mode="json"), modified)
            )
            assert draft.command_id == original_command
        with patch.dict(draft_executor.EXECUTOR_REGISTRY):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            invocation = {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": draft.model_dump(mode="json"),
            }
            result = await draft_executor._execute_confirmed_draft(
                invocation,
                {"configurable": {"thread_id": "space-update-flow"}},
                "space-update-flow",
                "fr",
            )
            assert result.success, result.to_agent_result()
            if scenario == "replay":
                replay = await draft_executor._execute_confirmed_draft(
                    invocation,
                    {"configurable": {"thread_id": "space-update-flow"}},
                    "space-update-flow",
                    "fr",
                )
                assert replay.success and replay.result_data == result.result_data
        actual = await async_session.get(RAGSpace, identity, populate_existing=True)
        assert not actual.is_active
        assert actual.name == (
            "Original personal space" if scenario == "edit" else "Confirmed rename"
        )
        assert actual.description == ("Edited purpose" if scenario == "edit" else None)
        assert (
            await async_session.scalar(
                select(func.count(AgentEffect.id)).where(AgentEffect.user_id == owner)
            )
            == 1
        )
        events = [queue.get_nowait() for _ in range(queue.qsize())]
        changes = [event for event in events if event.type == "application_state_changed"]
        assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == ["spaces"]
