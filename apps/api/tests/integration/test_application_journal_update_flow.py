"""Real edited journal proposals stay inert until exact durable confirmation."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_journal_tools
from src.domains.journals import manual_embeddings
from src.domains.journals.models import JournalEntry
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit"])
async def test_journal_update_real_hitl_and_editor(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    monkeypatch.setattr(settings, "journals_enabled", True)
    owner = test_user.id
    row = JournalEntry(
        user_id=owner, theme="learnings", title="Title", content="Original", char_count=8
    )
    async_session.add(row)
    await async_session.commit()
    entry_id = row.id
    calls: list[str] = []

    async def embed(text: str):
        calls.append(text)
        return None

    async def quota(actor_id, *, layer):
        assert actor_id == owner and layer == "journal_management"

    monkeypatch.setattr(manual_embeddings, "_generate_document_embedding", embed)
    monkeypatch.setattr(manual_embeddings, "enforce_usage_limit", quota)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "journal_update_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(application_journal_tools, "get_db_context", session)
    queue: asyncio.Queue[object] = asyncio.Queue()
    with installed_runtime_context(user_id=owner, deps=object(), side_channel_queue=queue):
        request = {"entry_id": str(entry_id), "changes": {"content": "Corrected"}}
        proposal = await application_journal_tools.update_lia_journal_entry_tool.coroutine(
            request=request, runtime=make_tool_runtime(user_id=owner, store=InMemoryStore())
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        assert calls == [] and queue.empty()
        await async_session.refresh(row)
        assert row.content == "Original"
        if scenario == "no_confirmation":
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
            assert calls == []
            return
        if scenario == "edit":
            request["changes"] = {"content": "Edited correction"}
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(draft.model_dump(mode="json"), {"intent": request})
            )
            assert calls == []
        with patch.dict(draft_executor.EXECUTOR_REGISTRY):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            result = await draft_executor._execute_confirmed_draft(
                {
                    "draft_id": item.id,
                    "draft_type": "application_action",
                    "draft_content": draft.model_dump(mode="json"),
                },
                {"configurable": {"thread_id": "journal-update-flow"}},
                "journal-update-flow",
                "fr",
            )
        assert result.success, result.to_agent_result()
        saved = await async_session.scalar(
            select(JournalEntry)
            .where(JournalEntry.id == entry_id)
            .execution_options(populate_existing=True)
        )
        assert (
            saved is not None
            and saved.content == request["changes"]["content"]
            and saved.revision == 2
        )
        assert len(calls) == 1
        changes = [
            event
            for event in (queue.get_nowait() for _ in range(queue.qsize()))
            if event.type == "application_state_changed"
        ]
        assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == ["journals"]
