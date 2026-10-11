"""The actual tool/durable HITL bridge starts source maintenance only after exact approval."""

import asyncio
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore

from src.core.config import settings
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.journal_consolidation_editing import (
    rebuild_journal_consolidation_draft,
)
from src.domains.agents.application.journal_consolidation_schemas import JournalConsolidationRequest
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_journal_tools import consolidate_lia_journals_tool
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime
from tests.integration.domains.journals.test_consolidation_integrity import (
    _answer,
    _entry,
    _user,
)
from tests.integration.domains.journals.test_consolidation_integrity import (
    isolated_runtime as isolated_runtime,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("edited", [False, True])
async def test_source_generation_waits_for_durable_human_confirmation(
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
        "journal_consolidation_editing",
    ]:
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr(
        "src.domains.agents.tools.application_journal_tools.get_db_context", session
    )
    model = _answer(monkeypatch, {"actions": [{"action": "delete", "entry_id": str(entry.id)}]})
    with installed_runtime_context(user_id=actor_id):
        proposal = await consolidate_lia_journals_tool.coroutine(
            request=JournalConsolidationRequest(scope="current_account"),
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        model.assert_not_called()
        await db.refresh(user)
        assert user.journal_last_attempted_at is None
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        if edited:
            revised = await rebuild_journal_consolidation_draft(
                draft, {"intent": {"scope": "current_account"}}
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

    changes = [
        event
        for event in (queue.get_nowait() for _ in range(queue.qsize()))
        if event.type == "application_state_changed"
    ]
    assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == ["journals"]
    assert changes[0].metadata["change"]["changed_fields"] == ["journal_consolidation"]
