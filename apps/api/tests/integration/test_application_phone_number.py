"""Real durable phone-number HITL, stale authority, editor and addressed invalidation."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.agents.application.command_repository import (
    cancel_command,
    get_command,
    matches_command,
)
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.services.hitl.draft_modifier import DraftModificationService
from src.domains.agents.tools.application_phone_tools import update_lia_phone_number_tool
from src.domains.telephony.identity import TelephonyIdentityService
from src.domains.telephony.number_gateway import SavedPhoneNumber
from src.domains.users.models import User
from src.infrastructure.phone_number_preferences import configure_phone_number_preferences
from tests.helpers.draft_refusals import draft_refusal_code
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention",
    [
        "set",
        "clear",
        "no_op",
        "number_change",
        "verification_change",
        "platform_off",
        "telephony_off",
        "cancel",
    ],
)
async def test_confirmed_number_change_uses_exact_owner_state_and_public_receipt(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "telephony_enabled", True)
    test_user.phone_number_encrypted = encrypt_data("+33612345678")
    test_user.phone_number_verified_at = datetime.now(UTC)
    test_user.phone_rich_context_enabled = True
    test_user.phone_disabled_domains = ["email"]
    await async_session.commit()
    actor_id, cipher, stamp = (
        test_user.id,
        test_user.phone_number_encrypted,
        test_user.phone_number_verified_at,
    )

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    previous = configure_phone_number_preferences(SavedPhoneNumber())
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
            change = (
                {"action": "clear"}
                if intervention == "clear"
                else {
                    "action": "set",
                    "phone_number": (
                        "+33612345678" if intervention == "no_op" else "+33 6 98 76 54 32"
                    ),
                }
            )
            proposal = await update_lia_phone_number_tool.coroutine(
                change=change,
                runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
            )
            assert proposal.success and proposal.metadata["requires_confirmation"]
            assert (
                test_user.phone_number_encrypted == cipher
                and test_user.phone_number_verified_at == stamp
            )
            item = next(iter(proposal.registry_updates.values()))
            assert cipher not in str(item.payload)
            if intervention == "number_change":
                await TelephonyIdentityService(async_session).set_number(actor_id, "+33600000000")
            elif intervention == "verification_change":
                test_user.phone_number_verified_at = stamp + timedelta(seconds=1)
                await async_session.commit()
            elif intervention == "platform_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            elif intervention == "telephony_off":
                monkeypatch.setattr(settings, "telephony_enabled", False)
            elif intervention == "cancel":
                assert await cancel_command(async_session, item.id, actor_id)
            draft_executor.register_executor("application_action", execute_application_action_draft)
            outcome = await draft_executor._execute_confirmed_draft(
                {
                    "draft_id": item.id,
                    "draft_type": "application_action",
                    "draft_content": item.payload["content"],
                },
                {"configurable": {"thread_id": "phone-number-confirmation"}},
                "phone-number-confirmation",
                "fr",
            )
        assert outcome.success is (intervention in {"set", "clear", "no_op"})
        assert "stored_digest" not in str(outcome.to_agent_result())
        assert "expected" not in str(outcome.to_agent_result()) and cipher not in str(
            outcome.to_agent_result()
        )
        await async_session.refresh(test_user)
        number = (
            decrypt_data(test_user.phone_number_encrypted)
            if test_user.phone_number_encrypted
            else None
        )
        expected_number = {
            "set": "+33698765432",
            "clear": None,
            "number_change": "+33600000000",
        }.get(intervention, "+33612345678")
        assert number == expected_number
        assert (
            test_user.phone_rich_context_enabled is True
            and test_user.phone_disabled_domains == ["email"]
        )
        if intervention in {"set", "clear", "number_change"}:
            assert test_user.phone_number_verified_at is None
        elif intervention == "no_op":
            assert (
                test_user.phone_number_encrypted == cipher
                and test_user.phone_number_verified_at == stamp
            )
        if intervention in {"number_change", "verification_change"}:
            assert draft_refusal_code(outcome) == "STALE_STATE"
        if intervention in {"platform_off", "telephony_off"}:
            assert draft_refusal_code(outcome) == "CAPABILITY_DISABLED"
            ledger.claim.assert_not_awaited()
        if intervention == "cancel":
            assert draft_refusal_code(outcome) == "CANCELLED"
            ledger.claim.assert_not_awaited()
        hints = [queue.get_nowait() for _ in range(queue.qsize())]
        hints = [event for event in hints if event.type == "application_state_changed"]
        assert len(hints) == int(intervention in {"set", "clear"})
        if hints:
            assert hints[0].metadata["change"]["resources"] == ["phone_identity"]
            assert hints[0].metadata["change"]["changed_fields"] == ["phone_number"]
            assert "+336" not in str(hints[0].metadata)
    finally:
        configure_phone_number_preferences(previous)


async def test_real_number_editor_replaces_pending_command_without_disclosing_comparison_material(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "telephony_enabled", True)
    await TelephonyIdentityService(async_session).set_number(test_user.id, "+33612345678")
    actor_id = test_user.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    previous = configure_phone_number_preferences(SavedPhoneNumber())
    llm = AsyncMock()
    llm.ainvoke.return_value = AIMessage(
        content=json.dumps({"intent": {"action": "clear"}, "remove_fields": []})
    )
    try:
        with (
            installed_runtime_context(user_id=actor_id, language="fr"),
            patch("src.domains.agents.tools.application_phone_tools.get_db_context", session),
            patch("src.domains.agents.application.command_service.get_db_context", session),
            patch("src.domains.agents.application.draft_editing.get_db_context", session),
            patch("src.domains.agents.services.hitl.draft_modifier.get_llm", return_value=llm),
        ):
            proposal = await update_lia_phone_number_tool.coroutine(
                change={"action": "set", "phone_number": "+33698765432"},
                runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
            )
            item = next(iter(proposal.registry_updates.values()))
            original = ApplicationActionDraftContent.model_validate(item.payload["content"])
            edited = await DraftModificationService().modify(
                original.model_dump(mode="json"),
                "Efface plutôt mon numéro",
                "application_action",
                user_language="fr",
                run_id=item.id,
            )
        revised = ApplicationActionDraftContent.model_validate(edited)
        command = await get_command(async_session, revised.command_id, actor_id)
        assert command is not None and matches_command(command, revised, item.id)
        assert not matches_command(command, original, item.id)
        assert revised.intent["phone_number"]["number"] is None
        prompt = str(llm.ainvoke.await_args)
        assert "stored_digest" not in prompt and "expected" not in prompt
        await async_session.refresh(test_user)
        assert decrypt_data(test_user.phone_number_encrypted) == "+33612345678"
    finally:
        configure_phone_number_preferences(previous)
