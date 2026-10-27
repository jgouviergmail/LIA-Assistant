"""Assistant preferences use the actual native draft dispatcher and SQL owner."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.preparation import prepare_assistant_content
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.services.streaming.voice_stream_helpers import _should_start_voice
from src.domains.agents.tools.application_read_tools import get_lia_assistant_preferences_tool
from src.domains.auth.preference_commands import (
    AssistantPreferencePatch,
    update_assistant_preferences,
)
from src.domains.users.models import User
from src.domains.users.service import UserService
from tests.helpers.draft_refusals import draft_refusal_code
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


async def test_turn_start_voice_snapshot_is_not_authority_after_a_saved_opt_out(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    test_user.voice_enabled = True
    await async_session.commit()
    before = await UserService(async_session).get_user_by_id(test_user.id)
    await update_assistant_preferences(
        async_session, test_user.id, AssistantPreferencePatch(voice_enabled=False)
    )
    assert before.voice_enabled is True
    with patch("src.infrastructure.database.session.get_db_context", session):
        assert await _should_start_voice(before, None, "voice-consent", "agent_parallel") is False
    test_user.is_active = False
    test_user.voice_enabled = True
    await async_session.commit()
    with patch("src.infrastructure.database.session.get_db_context", session):
        assert await _should_start_voice(before, None, "voice-consent", "sync_fallback") is False


@pytest.mark.parametrize("manual_intervention", [False, True])
async def test_consent_change_is_previewed_then_saved_only_if_still_current(
    async_session: AsyncSession, test_user: User, manual_intervention: bool
) -> None:
    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    test_user.memory_enabled = True
    await async_session.commit()
    revision = test_user.extraction_revision
    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    queue = asyncio.Queue()
    with (
        patch("src.domains.agents.tools.application_action_tools.get_db_context", session),
        patch("src.domains.agents.tools.application_read_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
        installed_runtime_context(
            user_id=test_user.id, deps=object(), language="fr", side_channel_queue=queue
        ),
    ):
        runtime = make_tool_runtime(user_id=test_user.id, store=InMemoryStore(), language="fr")
        read = await get_lia_assistant_preferences_tool.coroutine(
            fields=["memory_enabled"], runtime=runtime
        )
        assert read.success
        # Preserve the semantics of a consent draft already pending before rollout.
        content = await prepare_assistant_content(
            async_session, test_user.id, AssistantPreferencePatch(memory_enabled=False)
        )
        output = DraftService().create_draft(
            draft_type=DraftType.APPLICATION_ACTION,
            content=content.model_dump(mode="json"),
            source_tool="update_lia_assistant_preferences_tool",
            user_language="fr",
        )
        await save_command(async_session, content, next(iter(output.registry_updates)))
        assert output.success and output.metadata["requires_confirmation"]
        await async_session.refresh(test_user)
        assert test_user.memory_enabled is True
        assert test_user.extraction_revision == revision
        assert queue.empty()
        item = next(iter(output.registry_updates.values()))
        if manual_intervention:
            await update_assistant_preferences(
                async_session, test_user.id, AssistantPreferencePatch(memory_enabled=False)
            )
        draft_executor.register_executor("application_action", execute_application_action_draft)
        result = await draft_executor._execute_confirmed_draft(
            {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": item.payload["content"],
            },
            {"configurable": {"thread_id": "assistant-preferences-test"}},
            "assistant-confirmation",
            "fr",
        )
    await async_session.refresh(test_user)
    assert result.success is (not manual_intervention)
    assert not test_user.memory_enabled
    assert test_user.extraction_revision == revision + 1
    if manual_intervention:
        assert draft_refusal_code(result) == "STALE_STATE"
    changes = [queue.get_nowait() for _ in range(queue.qsize())]
    hints = [event for event in changes if event.type == "application_state_changed"]
    assert len(hints) == int(not manual_intervention)
    if hints:
        assert hints[0].metadata["change"]["changed_fields"] == ["memory_enabled"]
