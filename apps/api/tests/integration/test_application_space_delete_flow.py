"""A native space deletion reaches one effect ledger row through actual HITL confirmation."""

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
from src.domains.rag_spaces.models import RAGDocument, RAGSpace
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit", "retarget", "replay"])
@pytest.mark.parametrize("target", ["space", "document", "move"])
async def test_space_deletion_confirmation_flow(
    async_session, test_user, monkeypatch, tmp_path, scenario, target
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "src.domains.agents.application.document_move_scope.get_reindex_status",
        AsyncMock(return_value={"in_progress": False}),
    )
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Confirmed personal removal")
    async_session.add(space)
    await async_session.commit()
    identity = space.id
    space_id = space.id
    model = RAGSpace
    request = {"space_id": identity}
    tool = application_space_tools.delete_lia_knowledge_space_tool
    destination_id = None
    if target != "space":
        document = RAGDocument(
            user_id=owner,
            space_id=space_id,
            filename="confirmed.txt",
            original_filename="Confirmed document.txt",
            file_size=4,
            content_type="text/plain",
            status="ready",
        )
        async_session.add(document)
        await async_session.commit()
        identity, model = document.id, RAGDocument
        directory = tmp_path / str(owner) / str(space_id)
        directory.mkdir(parents=True)
        (directory / "confirmed.txt").write_bytes(b"data")
        request = {"space_id": space_id, "document_ids": [identity]}
        tool = application_space_tools.delete_lia_knowledge_documents_tool
        if target == "move":
            destination = RAGSpace(user_id=owner, name="Confirmed target")
            async_session.add(destination)
            await async_session.commit()
            destination_id = destination.id
            request["target_space_id"] = destination_id
            tool = application_space_tools.move_lia_knowledge_documents_tool

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
        "space_delete_editing",
        "document_delete_editing",
        "document_move_editing",
    ):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr(application_space_tools, "get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    queue = asyncio.Queue()
    with installed_runtime_context(user_id=owner, deps=object(), side_channel_queue=queue):
        proposal = await tool.coroutine(
            request=request,
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert (
            proposal.success and proposal.metadata["requires_confirmation"]
        ), proposal.model_dump()
        assert await async_session.get(model, identity)
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
                "intent": {"space_id": str(uuid4() if scenario == "retarget" else identity)}
            }
            if target != "space":
                modified = {
                    "intent": {
                        "space_id": str(space_id),
                        "document_ids": [str(uuid4() if scenario == "retarget" else identity)],
                    }
                }
                if target == "move":
                    modified["intent"]["target_space_id"] = str(destination_id)
            if scenario == "retarget":
                with pytest.raises(CommandRejected, match="INVALID_INPUT"):
                    await rebuild_application_draft(draft.model_dump(mode="json"), modified)
                return
            original = draft.command_id
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(draft.model_dump(mode="json"), modified)
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
                {"configurable": {"thread_id": "space-delete-flow"}},
                "space-delete-flow",
                "fr",
            )
            assert result.success, result.to_agent_result()
            if scenario == "replay":
                replay = await draft_executor._execute_confirmed_draft(
                    invocation,
                    {"configurable": {"thread_id": "space-delete-flow"}},
                    "space-delete-flow",
                    "fr",
                )
                assert replay.success and replay.result_data == result.result_data
        if target == "move":
            moved = await async_session.get(RAGDocument, identity, populate_existing=True)
            assert moved.space_id == destination_id
            assert (
                tmp_path / str(owner) / str(destination_id) / "confirmed.txt"
            ).read_bytes() == b"data"
        else:
            assert await async_session.get(model, identity, populate_existing=True) is None
        if target != "space":
            assert await async_session.get(RAGSpace, space_id, populate_existing=True)
            assert not (tmp_path / str(owner) / str(space_id) / "confirmed.txt").exists()
        assert (
            await async_session.scalar(
                select(func.count(AgentEffect.id)).where(AgentEffect.user_id == owner)
            )
            == 1
        )
        events = [queue.get_nowait() for _ in range(queue.qsize())]
        changes = [event for event in events if event.type == "application_state_changed"]
        assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == ["spaces"]
