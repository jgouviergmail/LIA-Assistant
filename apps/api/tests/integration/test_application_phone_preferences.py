"""Actual saved phone owner and durable confirmed commands; no real calls or providers."""

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
from src.core.security.utils import encrypt_data
from src.domains.agents.application.command_repository import get_command, matches_command
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.services.hitl.draft_modifier import DraftModificationService
from src.domains.agents.tools.application_phone_tools import update_lia_phone_preferences_tool
from src.domains.telephony.preference_commands import update_phone_preferences
from src.domains.telephony.preference_gateway import SavedPhonePreferences
from src.domains.telephony.schemas import TelephonyIdentityUpdateRequest
from src.domains.users.models import User
from src.infrastructure.phone_preferences import configure_phone_preferences
from tests.helpers.draft_refusals import draft_refusal_code
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention",
    [
        "none",
        "manual_change",
        "number_change",
        "platform_off",
        "telephony_off",
        "no_op",
    ],
)
async def test_phone_confirmation_preserves_identity_and_requires_current_state_and_authority(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "telephony_enabled", True)
    test_user.phone_rich_context_enabled = True
    test_user.phone_disabled_domains = ["email"]
    test_user.phone_call_mode = "delegated"
    test_user.phone_number_encrypted = encrypt_data("+33612345678")
    await async_session.commit()
    actor_id = test_user.id
    number = test_user.phone_number_encrypted

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    previous = configure_phone_preferences(SavedPhonePreferences())
    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    queue: asyncio.Queue[object] = asyncio.Queue()
    try:
        with (
            installed_runtime_context(
                user_id=actor_id, language="fr", deps=object(), side_channel_queue=queue
            ),
            patch("src.domains.agents.tools.application_phone_tools.get_db_context", session),
            patch("src.domains.agents.application.command_service.get_db_context", session),
            patch("src.domains.agents.application.draft_execution.get_db_context", session),
            patch("src.domains.agents.effects.runtime._LEDGER", ledger),
            patch.dict(draft_executor.EXECUTOR_REGISTRY),
        ):
            proposal = await update_lia_phone_preferences_tool.coroutine(
                change={"rich_context_enabled": intervention == "no_op"},
                runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
            )
            assert proposal.success and proposal.metadata["requires_confirmation"]
            assert test_user.phone_rich_context_enabled is True
            item = next(iter(proposal.registry_updates.values()))
            assert number not in str(item.payload)
            if intervention == "manual_change":
                await update_phone_preferences(
                    async_session, actor_id, TelephonyIdentityUpdateRequest(call_mode="direct")
                )
            elif intervention == "number_change":
                test_user.phone_number_encrypted = encrypt_data("+33600000000")
                await async_session.commit()
            elif intervention == "platform_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            elif intervention == "telephony_off":
                monkeypatch.setattr(settings, "telephony_enabled", False)
            draft_executor.register_executor("application_action", execute_application_action_draft)
            outcome = await draft_executor._execute_confirmed_draft(
                {
                    "draft_id": item.id,
                    "draft_type": "application_action",
                    "draft_content": item.payload["content"],
                },
                {"configurable": {"thread_id": "phone-confirmation"}},
                "phone-confirmation",
                "fr",
            )
        assert outcome.success is (intervention in {"none", "no_op"})
        assert "stored_digest" not in str(outcome.to_agent_result())
        await async_session.refresh(test_user)
        assert test_user.phone_rich_context_enabled is (intervention != "none")
        assert test_user.phone_disabled_domains == ["email"]
        assert test_user.phone_call_mode == (
            "direct" if intervention == "manual_change" else "delegated"
        )
        if intervention != "number_change":
            assert test_user.phone_number_encrypted == number
        if intervention in {"manual_change", "number_change"}:
            assert draft_refusal_code(outcome) == "STALE_STATE"
        if intervention in {"platform_off", "telephony_off"}:
            assert draft_refusal_code(outcome) == "CAPABILITY_DISABLED"
            ledger.claim.assert_not_awaited()
        hints = [queue.get_nowait() for _ in range(queue.qsize())]
        hints = [event for event in hints if event.type == "application_state_changed"]
        assert len(hints) == int(intervention == "none")
        if hints:
            assert hints[0].metadata["change"]["resources"] == ["phone_identity"]
            assert "+336" not in str(hints[0].metadata)
    finally:
        configure_phone_preferences(previous)


async def test_phone_editor_replaces_pending_identity_without_disclosing_private_snapshot(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "telephony_enabled", True)
    test_user.phone_rich_context_enabled = True
    test_user.phone_disabled_domains = ["email"]
    test_user.phone_call_mode = "delegated"
    test_user.phone_number_encrypted = encrypt_data("+33612345678")
    await async_session.commit()
    actor_id = test_user.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    previous = configure_phone_preferences(SavedPhonePreferences())
    llm = AsyncMock()
    llm.ainvoke.return_value = AIMessage(
        content=json.dumps({"intent": {"call_mode": "direct"}, "remove_fields": []})
    )
    try:
        with (
            installed_runtime_context(user_id=actor_id, language="fr"),
            patch("src.domains.agents.tools.application_phone_tools.get_db_context", session),
            patch("src.domains.agents.application.command_service.get_db_context", session),
            patch("src.domains.agents.application.draft_editing.get_db_context", session),
            patch("src.domains.agents.services.hitl.draft_modifier.get_llm", return_value=llm),
        ):
            proposal = await update_lia_phone_preferences_tool.coroutine(
                change={"call_mode": "delegated"},
                runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
            )
            item = next(iter(proposal.registry_updates.values()))
            original = ApplicationActionDraftContent.model_validate(item.payload["content"])
            edited = await DraftModificationService().modify(
                original.model_dump(mode="json"),
                "Choisis plutôt direct",
                "application_action",
                user_language="fr",
                run_id=item.id,
            )
        revised = ApplicationActionDraftContent.model_validate(edited)
        assert revised.intent["phone_preferences"]["values"]["call_mode"] == "direct"
        command = await get_command(async_session, original.command_id, actor_id)
        assert command is not None and matches_command(command, revised, item.id)
        assert not matches_command(command, original, item.id)
        await async_session.refresh(test_user)
        assert test_user.phone_call_mode == "delegated"
        prompt = str(llm.ainvoke.call_args.args[0])
        assert "stored_digest" not in prompt and test_user.phone_number_encrypted not in prompt
    finally:
        configure_phone_preferences(previous)
