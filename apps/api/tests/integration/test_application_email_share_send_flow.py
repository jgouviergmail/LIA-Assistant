"""Original email HITL sends once and files the acknowledged action through the original register."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import func, select

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_email_share_tools
from src.domains.bookmarks.models import MessageBookmark
from src.domains.email_share.service import ShareRoute
from src.domains.shared.action_sink import EMAIL_SHARE_CAPABILITY
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context
from tests.integration.domains.bookmarks.test_bookmarks_db import _bookmark

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize("confirmed", [False, True])
async def test_original_saved_answer_tool_confirmation_and_owned_refresh(
    async_session, test_user, monkeypatch, mode, confirmed
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "bookmarks_enabled", True)
    monkeypatch.setattr(settings, "bookmarks_max_per_user", 100)
    monkeypatch.setattr(settings, "email_share_enabled", True)
    owner = test_user.id
    saved = await _bookmark(async_session, test_user, None)
    bookmark_id = saved.id
    await async_session.commit()

    sends = []
    recorder = AsyncMock()
    recorder.claim.return_value = "controlled-email-action"
    monkeypatch.setattr("src.domains.shared.action_sink._recorder", recorder)
    monkeypatch.setattr(
        "src.domains.agents.application.email_share_send.resolve_route",
        AsyncMock(return_value=ShareRoute.relay(test_user.email, max_file_bytes=100_000)),
    )
    monkeypatch.setattr(
        "src.domains.agents.application.email_share_send.rate_limit_email_share", AsyncMock()
    )

    async def relay(prepared, attachment):
        assert not async_session.in_transaction()
        sends.append(attachment.data)

    monkeypatch.setattr("src.domains.email_share.service._send_from_relay", relay)

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
    monkeypatch.setattr(application_email_share_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    events = asyncio.Queue()
    with installed_runtime_context(
        user_id=owner, deps=object(), execution_mode=mode, side_channel_queue=events
    ):
        proposal = await application_email_share_tools.send_lia_email_share_tool.coroutine(
            request={
                "subject": "Actual subject",
                "attachment": {"kind": "saved_answer", "bookmark_id": bookmark_id},
            },
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
            == 1
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
                    {"configurable": {"thread_id": "email-share-flow"}},
                    "email-share-flow",
                    "fr",
                )
            assert result.success and result.result_data["committed"]
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
        assert (
            await async_session.scalar(
                select(func.count(MessageBookmark.id)).where(MessageBookmark.user_id == owner)
            )
            == 1
        )
        assert len(sends) == int(confirmed)
        assert recorder.claim.await_count == int(confirmed)
        if confirmed:
            assert recorder.claim.await_args.kwargs["capability"] == EMAIL_SHARE_CAPABILITY
            assert recorder.claim.await_args.kwargs["user_id"] == owner
            recorder.settle.assert_awaited_once_with("controlled-email-action", succeeded=True)
        changes = []
        while not events.empty():
            event = events.get_nowait()
            if event.type == "application_state_changed":
                changes.append(event)
        assert len(changes) == int(confirmed)
        if confirmed:
            assert changes[0].metadata["change"]["resources"] == ["generated_assets"]
            assert changes[0].metadata["change"]["changed_fields"] == ["email_to_send"]
