"""A real confirmed debrief reaches the source claim once; edits and replay retain authority."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select

from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_relation_tools
from src.domains.relations.debrief.models import RelationDebrief
from src.domains.relations.overview import OverviewEvidence
from src.domains.relations.schemas import RelationDetail
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit", "replay"])
async def test_debrief_real_confirmation_edits_and_replay(
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

    for module in (
        "command_service",
        "draft_execution",
        "relation_debrief_build_editing",
        "relation_debrief_build",
    ):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(application_relation_tools, "get_db_context", session)
    monkeypatch.setattr("src.domains.relations.debrief.service.get_db_context", session)
    detail = RelationDetail(
        display_name="Alice",
        identity_confidence="exact",
        open_loops=[],
        recent_calls=[],
        memories=[],
    )
    monkeypatch.setattr(
        "src.domains.relations.debrief.service.build_overview_evidence",
        AsyncMock(return_value=OverviewEvidence(detail=detail, blocks={}, unavailable=[])),
    )
    monkeypatch.setattr(
        "src.domains.relations.debrief.service.RelationDebriefService._record_consultations",
        lambda *args: None,
    )

    queue = asyncio.Queue()
    with installed_runtime_context(user_id=owner, deps=object(), side_channel_queue=queue):
        proposal = await application_relation_tools.generate_lia_relation_debrief_tool.coroutine(
            request={"name": "Alice", "force": False},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        assert (
            await async_session.scalar(
                select(RelationDebrief.id).where(RelationDebrief.user_id == owner)
            )
            is None
        )
        if scenario == "no_confirmation":
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
            return
        if scenario == "edit":
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(
                    draft.model_dump(mode="json"),
                    {"intent": {"name": "Carol", "force": False}},
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
                {"configurable": {"thread_id": "relation-debrief-flow"}},
                "relation-debrief-flow",
                "fr",
            )
            assert result.success, result.to_agent_result()
            if scenario == "replay":
                with patch(
                    "src.domains.relations.debrief.service.RelationDebriefService.build",
                    side_effect=AssertionError("No second debrief claim or work"),
                ) as write:
                    replay = await draft_executor._execute_confirmed_draft(
                        invocation,
                        {"configurable": {"thread_id": "relation-debrief-flow"}},
                        "relation-debrief-flow",
                        "fr",
                    )
                assert replay.success and replay.result_data == result.result_data
                write.assert_not_called()
        assert await async_session.scalar(
            select(RelationDebrief.name_key).where(RelationDebrief.user_id == owner)
        ) == ("carol" if scenario == "edit" else "alice")
        changes = [
            event
            for event in (queue.get_nowait() for _ in range(queue.qsize()))
            if event.type == "application_state_changed"
        ]
        assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == ["relations"]
