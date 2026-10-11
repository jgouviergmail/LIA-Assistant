"""The favorite tool proposes only; exact human approval is required for the source write."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore

from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_relation_tools
from src.domains.relations.favorite_commands import read_relation_favorite
from src.domains.relations.models import RelationFavorite
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit", "replay"])
async def test_favorite_exact_confirmation_has_one_source_write_and_owned_hint(
    async_session, test_user, monkeypatch, scenario
):
    owner = test_user.id
    async_session.add(RelationFavorite(user_id=owner, name_key="alice", display_name="Alice"))
    await async_session.commit()

    @asynccontextmanager
    async def session():
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "relation_favorite_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(application_relation_tools, "get_db_context", session)
    queue = asyncio.Queue()
    with installed_runtime_context(user_id=owner, deps=object(), side_channel_queue=queue):
        proposal = await application_relation_tools.set_lia_relation_favorite_tool.coroutine(
            request={"name": "Alice", "starred": False},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        assert (await read_relation_favorite(async_session, owner, "Alice")).starred
        assert queue.empty()
        if scenario == "no_confirmation":
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
            return
        if scenario == "edit":
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(
                    draft.model_dump(mode="json"), {"intent": {"name": "Bob", "starred": True}}
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
                {"configurable": {"thread_id": "relation-favorite-flow"}},
                "relation-favorite-flow",
                "fr",
            )
            assert result.success, result.to_agent_result()
            if scenario == "replay":
                with patch(
                    "src.domains.agents.application.relation_favorite.set_managed_relation_favorite",
                    side_effect=AssertionError("No second write"),
                ) as write:
                    replay = await draft_executor._execute_confirmed_draft(
                        invocation,
                        {"configurable": {"thread_id": "relation-favorite-flow"}},
                        "relation-favorite-flow",
                        "fr",
                    )
                assert replay.success and replay.result_data == result.result_data
                write.assert_not_called()
        assert (await read_relation_favorite(async_session, owner, "Alice")).starred is (
            scenario == "edit"
        )
        if scenario == "edit":
            assert (await read_relation_favorite(async_session, owner, "Bob")).starred
        changes = [
            event
            for event in (queue.get_nowait() for _ in range(queue.qsize()))
            if event.type == "application_state_changed"
        ]
        assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == ["relations"]
