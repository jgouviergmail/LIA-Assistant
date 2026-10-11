"""Real tool output must become a durable, edited and exactly confirmed removal."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_journal_tools
from src.domains.journals.models import JournalEntry
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit"])
async def test_journal_removal_real_hitl_and_editor(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    monkeypatch.setattr(settings, "journals_enabled", True)
    owner = test_user.id
    rows = [
        JournalEntry(user_id=owner, theme="learnings", title=str(i), content="Owned", char_count=5)
        for i in range(2)
    ]
    async_session.add_all(rows)
    await async_session.commit()
    selected_id = rows[0].id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "journal_removal_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(application_journal_tools, "get_db_context", session)
    queue: asyncio.Queue[object] = asyncio.Queue()
    with installed_runtime_context(user_id=owner, deps=object(), side_channel_queue=queue):
        proposal = await application_journal_tools.delete_lia_journal_entries_tool.coroutine(
            request={"entry_id": str(selected_id)},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        count_query = (
            select(func.count()).select_from(JournalEntry).where(JournalEntry.user_id == owner)
        )
        assert await async_session.scalar(count_query) == 2 and queue.empty()
        if scenario == "no_confirmation":
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
            return
        if scenario == "edit":
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(
                    draft.model_dump(mode="json"), {"intent": {"entry_id": None}}
                )
            )
            assert draft.before["journal_entries_to_delete"]["entries"] == 2
        with patch.dict(draft_executor.EXECUTOR_REGISTRY):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            result = await draft_executor._execute_confirmed_draft(
                {
                    "draft_id": item.id,
                    "draft_type": "application_action",
                    "draft_content": draft.model_dump(mode="json"),
                },
                {"configurable": {"thread_id": "journal-removal-flow"}},
                "journal-removal-flow",
                "fr",
            )
        assert result.success, result.to_agent_result()
        assert await async_session.scalar(count_query) == (0 if scenario == "edit" else 1)
        changes = [
            event
            for event in (queue.get_nowait() for _ in range(queue.qsize()))
            if event.type == "application_state_changed"
        ]
        assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == ["journals"]
