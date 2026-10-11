"""Real native proposal and durable HITL cannot mutate before approval or reuse old approval."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.journal_settings import prepare_journal_settings
from src.domains.agents.application.journal_settings_schemas import JournalSettingsPatch
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_journal_tools
from src.domains.users.models import User
from tests.helpers.application_pending_proposal import pending_proposal
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit"])
async def test_journal_settings_require_exact_durable_confirmation_and_publish_one_owned_hint(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    monkeypatch.setattr(settings, "journals_enabled", True)
    owner = test_user.id
    test_user.journals_enabled = True
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "journal_settings_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(application_journal_tools, "get_db_context", session)
    queue: asyncio.Queue[object] = asyncio.Queue()
    with installed_runtime_context(user_id=owner, deps=object(), side_channel_queue=queue):
        proposal = await pending_proposal(
            async_session,
            test_user.id,
            JournalSettingsPatch.model_validate({"journals_enabled": False}),
            "update_lia_journal_settings_tool",
            prepare_journal_settings,
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        await async_session.refresh(test_user)
        assert test_user.journals_enabled and queue.empty()
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
                    {"intent": {"journals_enabled": False, "journal_context_max_results": 1}},
                )
            )
        with patch.dict(draft_executor.EXECUTOR_REGISTRY):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            result = await draft_executor._execute_confirmed_draft(
                {
                    "draft_id": item.id,
                    "draft_type": "application_action",
                    "draft_content": draft.model_dump(mode="json"),
                },
                {"configurable": {"thread_id": "journal-settings-flow"}},
                "journal-settings-flow",
                "fr",
            )
        assert result.success, result.to_agent_result()
        await async_session.refresh(test_user)
        assert not test_user.journals_enabled
        if scenario == "edit":
            assert test_user.journal_context_max_results == 1
        changes = [
            event
            for event in (queue.get_nowait() for _ in range(queue.qsize()))
            if event.type == "application_state_changed"
        ]
        assert len(changes) == 1
        assert changes[0].metadata["change"]["resources"] == ["journals"]
