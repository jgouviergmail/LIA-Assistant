"""Real exact HITL, public amendment and durable replay reach provider work once."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.store.memory import InMemoryStore

from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_relation_tools
from src.domains.relations.providers.schemas import ContextSection, ContextStatus, RelationContext
from src.domains.relations.providers.service import RelationContextService
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit", "replay"])
async def test_context_refresh_real_confirmation_edits_and_replay(
    async_session, test_user, monkeypatch, scenario
):
    owner = test_user.id
    await async_session.commit()

    @asynccontextmanager
    async def session():
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "relation_context_refresh_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(application_relation_tools, "get_db_context", session)
    section = ContextSection(status=ContextStatus.EMPTY, generated_at=datetime.now(UTC))
    calls = AsyncMock(return_value=RelationContext(contact=section, emails=section, events=section))

    async def fetch(service, name, **kwargs):
        assert service.user_id == owner
        return await calls(name, **kwargs)

    monkeypatch.setattr(RelationContextService, "build", fetch)
    queue = asyncio.Queue()
    with installed_runtime_context(user_id=owner, deps=object(), side_channel_queue=queue):
        proposal = await application_relation_tools.refresh_lia_relation_context_tool.coroutine(
            request={"name": "Alice", "sections": ["emails"]},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        calls.assert_not_awaited()
        if scenario == "no_confirmation":
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
            calls.assert_not_awaited()
            return
        if scenario == "edit":
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(
                    draft.model_dump(mode="json"),
                    {"intent": {"name": "Carol", "sections": ["events"]}},
                )
            )
        with patch.dict(draft_executor.EXECUTOR_REGISTRY):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            invocation = {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": draft.model_dump(mode="json"),
            }
            result = await draft_executor._execute_confirmed_draft(
                invocation,
                {"configurable": {"thread_id": "relation-context-flow"}},
                "relation-context-flow",
                "fr",
            )
            assert result.success, result.to_agent_result()
            if scenario == "replay":
                replay = await draft_executor._execute_confirmed_draft(
                    invocation,
                    {"configurable": {"thread_id": "relation-context-flow"}},
                    "relation-context-flow",
                    "fr",
                )
                assert replay.success and replay.result_data == result.result_data
        calls.assert_awaited_once()
        assert calls.await_args.args[0] == ("Carol" if scenario == "edit" else "Alice")
        assert calls.await_args.kwargs["refresh"] == frozenset(
            {"events" if scenario == "edit" else "emails"}
        )
        changes = [
            event
            for event in (queue.get_nowait() for _ in range(queue.qsize()))
            if event.type == "application_state_changed"
        ]
        assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == ["relations"]
