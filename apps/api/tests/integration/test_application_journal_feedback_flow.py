"""The actual feedback tool/durable HITL bridge saves a correction and refreshes the owned UI."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.store.memory import InMemoryStore

from src.core.config import settings
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.journal_feedback_editing import (
    rebuild_journal_feedback_draft,
)
from src.domains.agents.application.journal_feedback_schemas import JournalFeedbackRequest
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_journal_tools import (
    submit_lia_journal_portrait_feedback_tool,
)
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context
from tests.integration.domains.journals.test_consolidation_integrity import (
    _answer,
    _entry,
    _user,
)
from tests.integration.domains.journals.test_consolidation_integrity import (
    isolated_runtime as isolated_runtime,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("edited", [False, True])
async def test_full_feedback_and_source_generation_wait_for_durable_confirmation(
    isolated_runtime, monkeypatch, edited
):
    db = isolated_runtime
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "journals_enabled", True)
    user = await _user(db)
    entry = await _entry(db, user)
    actor_id = user.id
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def session():
        yield db
        await db.commit()

    for module in [
        "command_service",
        "draft_execution",
        "journal_consolidation",
        "journal_feedback_editing",
    ]:
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr(
        "src.domains.agents.tools.application_journal_tools.get_db_context", session
    )
    monkeypatch.setattr(
        "src.domains.journals.manual_embeddings._generate_document_embedding",
        AsyncMock(return_value=None),
    )
    model = _answer(monkeypatch, {"actions": [{"action": "delete", "entry_id": str(entry.id)}]})
    with installed_runtime_context(user_id=actor_id):
        proposal = await submit_lia_journal_portrait_feedback_tool.coroutine(
            request=JournalFeedbackRequest(comment="Correction"),
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        model.assert_not_called()
        await db.refresh(user)
        assert user.journal_last_attempted_at is None
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        if edited:
            revised = await rebuild_journal_feedback_draft(
                draft, {"intent": {"comment": "Edited complete correction"}}
            )
            draft = ApplicationActionDraftContent.model_validate(revised)
    queue = asyncio.Queue()
    with (
        installed_runtime_context(user_id=actor_id, deps=object(), side_channel_queue=queue),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
    ):
        draft_executor.register_executor("application_action", execute_application_action_draft)
        result = await draft_executor._execute_confirmed_draft(
            {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": draft.model_dump(mode="json"),
            },
            {"configurable": {"thread_id": "journal-consolidation-flow"}},
            "journal-consolidation-flow",
            "fr",
        )
    assert result.to_agent_result()["status"] == "success"
    model.assert_awaited_once()
    from sqlalchemy import select

    from src.domains.journals.models import JournalEntry

    saved = await db.scalar(select(JournalEntry).where(JournalEntry.id == draft.command_id))
    assert saved is not None and saved.content == (
        "Edited complete correction" if edited else "Correction"
    )

    changes = [
        event
        for event in (queue.get_nowait() for _ in range(queue.qsize()))
        if event.type == "application_state_changed"
    ]
    assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == ["journals"]
    assert changes[0].metadata["change"]["changed_fields"] == ["journal_feedback"]
