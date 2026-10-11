"""Native live confirmation against PostgreSQL; shared effect ledger is controlled."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_repository import get_command, matches_command
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.services.hitl.draft_modifier import DraftModificationService
from src.domains.agents.tools.application_live_tools import update_lia_live_preferences_tool
from src.domains.live.preference_commands import update_live_preferences
from src.domains.live.preference_gateway import SavedLivePreferences
from src.domains.live.preferences import LivePreferences
from src.domains.users.models import User
from src.infrastructure.live_preferences import configure_live_preferences
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention",
    ["none", "manual_change", "provider_change", "platform_off", "live_off", "no_op"],
)
async def test_live_confirmation_preserves_provider_and_refuses_changed_authority_or_state(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "live_enabled", True)
    test_user.live_preferences = LivePreferences(provider="gemini").model_dump()
    await async_session.commit()
    actor_id = test_user.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    configure_live_preferences(SavedLivePreferences())
    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    queue: asyncio.Queue[object] = asyncio.Queue()
    with (
        installed_runtime_context(
            user_id=actor_id, language="fr", deps=object(), side_channel_queue=queue
        ),
        patch("src.domains.agents.tools.application_live_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
    ):
        proposal = await update_lia_live_preferences_tool.coroutine(
            change={"end_of_speech": "normal" if intervention == "no_op" else "calm"},
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        item = next(iter(proposal.registry_updates.values()))
        assert proposal.success and proposal.metadata["requires_confirmation"]
        assert test_user.live_preferences["end_of_speech"] == "normal"
        draft_executor.register_executor("application_action", execute_application_action_draft)
        if intervention in {"manual_change", "provider_change"}:
            await update_live_preferences(
                async_session,
                actor_id,
                LivePreferences(
                    end_of_speech="lively" if intervention == "manual_change" else "normal",
                    provider="openai" if intervention == "provider_change" else "gemini",
                ),
            )
        if intervention == "platform_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        if intervention == "live_off":
            monkeypatch.setattr(settings, "live_enabled", False)
        outcome = await draft_executor._execute_confirmed_draft(
            {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": item.payload["content"],
            },
            {"configurable": {"thread_id": "live-confirmation"}},
            "live-confirmation",
            "fr",
        )
    assert outcome.success is (intervention in {"none", "no_op"})
    if outcome.success:
        assert "stored_digest" not in str(outcome.to_agent_result())
        assert "_draft_content" not in outcome.result_data
    await async_session.refresh(test_user)
    assert test_user.live_preferences["provider"] == (
        "openai" if intervention == "provider_change" else "gemini"
    )
    expected = (
        "calm"
        if intervention == "none"
        else "lively" if intervention == "manual_change" else "normal"
    )
    assert test_user.live_preferences["end_of_speech"] == expected
    if intervention in {"manual_change", "provider_change"}:
        assert outcome.error == "STALE_STATE"
    if intervention in {"platform_off", "live_off"}:
        assert outcome.error == "CAPABILITY_DISABLED"
        ledger.claim.assert_not_awaited()
    hints = [queue.get_nowait() for _ in range(queue.qsize())]
    hints = [event for event in hints if event.type == "application_state_changed"]
    assert len(hints) == int(intervention == "none")
    if hints:
        assert hints[0].metadata["change"]["resources"] == ["live_preferences"]
        assert "gemini" not in str(hints[0].metadata)


async def test_live_editor_replaces_the_exact_pending_command_without_provider_metadata(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "live_enabled", True)
    test_user.live_preferences = LivePreferences(provider="gemini").model_dump()
    await async_session.commit()
    actor_id = test_user.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    configure_live_preferences(SavedLivePreferences())
    llm = AsyncMock()
    llm.ainvoke.return_value = AIMessage(
        content=json.dumps(
            {
                "intent": {"end_of_speech": "lively"},
                "remove_fields": [],
            }
        )
    )
    with (
        installed_runtime_context(user_id=actor_id, language="fr"),
        patch("src.domains.agents.tools.application_live_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
        patch("src.domains.agents.services.hitl.draft_modifier.get_llm", return_value=llm),
    ):
        proposal = await update_lia_live_preferences_tool.coroutine(
            change={"end_of_speech": "calm"},
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        item = next(iter(proposal.registry_updates.values()))
        original = ApplicationActionDraftContent.model_validate(item.payload["content"])
        edited = await DraftModificationService().modify(
            original.model_dump(mode="json"),
            "Choisis plutôt lively",
            "application_action",
            user_language="fr",
            run_id=item.id,
        )
    revised = ApplicationActionDraftContent.model_validate(edited)
    assert revised.intent["live_reflexes"]["values"]["end_of_speech"] == "lively"
    command = await get_command(async_session, original.command_id, actor_id)
    assert command is not None and matches_command(command, revised, item.id)
    assert not matches_command(command, original, item.id)
    await async_session.refresh(test_user)
    assert test_user.live_preferences["end_of_speech"] == "normal"
    prompt = str(llm.ainvoke.call_args.args[0])
    assert "gemini" not in prompt and "stored_digest" not in prompt
