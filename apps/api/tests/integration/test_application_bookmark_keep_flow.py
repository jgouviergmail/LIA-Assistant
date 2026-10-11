"""The actual native tool saves only through original HITL and addresses its owner's gallery."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import func, select

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_bookmark_tools
from src.domains.bookmarks.models import MessageBookmark
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime
from tests.integration.domains.bookmarks.test_bookmarks_db import _conversation, _message

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize("confirmed", [False, True])
async def test_original_saved_answer_tool_confirmation_and_owned_refresh(
    async_session, test_user, monkeypatch, mode, confirmed
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "bookmarks_enabled", True)
    monkeypatch.setattr(settings, "bookmarks_max_per_user", 100)
    owner = test_user.id
    conversation = await _conversation(async_session, test_user)
    answer = await _message(
        async_session, conversation, role="assistant", content="Approved actual answer", minutes=1
    )
    message_id = answer.id
    await async_session.commit()
    monkeypatch.setattr(
        "src.domains.agents.application.bookmark_keep.enqueue_bookmark_index", lambda identity: None
    )

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
    monkeypatch.setattr(application_bookmark_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    events = asyncio.Queue()
    with installed_runtime_context(
        user_id=owner, deps=object(), execution_mode=mode, side_channel_queue=events
    ):
        proposal = await application_bookmark_tools.keep_lia_saved_answer_tool.coroutine(
            request={"message_id": message_id},
            runtime=make_tool_runtime(
                user_id=owner, store=InMemoryStore(), execution_mode=mode, side_channel_queue=events
            ),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        assert (
            await async_session.scalar(
                select(func.count(MessageBookmark.id)).where(MessageBookmark.user_id == owner)
            )
            == 0
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
                    {"configurable": {"thread_id": "bookmark-keep-flow"}},
                    "bookmark-keep-flow",
                    "fr",
                )
            assert result.success and result.result_data["committed"]
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
        assert await async_session.scalar(
            select(func.count(MessageBookmark.id)).where(MessageBookmark.user_id == owner)
        ) == int(confirmed)
        changes = []
        while not events.empty():
            event = events.get_nowait()
            if event.type == "application_state_changed":
                changes.append(event)
        assert len(changes) == int(confirmed)
        if confirmed:
            assert changes[0].metadata["change"]["resources"] == ["generated_assets"]
            assert changes[0].metadata["change"]["changed_fields"] == ["saved_answer_to_keep"]
