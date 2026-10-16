"""Actual SQL device registrations and native confirmation; ledger callbacks are controlled."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundError
from src.domains.agents.application.command_repository import get_command, matches_command
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.services.hitl.draft_modifier import DraftModificationService
from src.domains.agents.tools.application_notification_tools import (
    get_lia_notification_devices_tool,
    remove_lia_notification_device_tool,
)
from src.domains.notifications.device_gateway import SavedNotificationDevices
from src.domains.notifications.models import UserFCMToken
from src.domains.notifications.router import delete_token_by_id
from src.domains.users.models import User
from src.infrastructure.notification_devices import configure_notification_devices
from tests.helpers.draft_refusals import draft_refusal_code
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


async def test_foreign_notification_devices_are_hidden_and_cannot_be_removed_through_ui_or_tool(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    owner = User(id=uuid4(), email=f"device-owner-{uuid4()}@example.test", is_active=True)
    async_session.add(owner)
    await async_session.flush()
    foreign = UserFCMToken(
        id=uuid4(),
        user_id=owner.id,
        token="foreign-private-token",
        device_type="web",
        device_name="Foreign browser",
        is_active=True,
    )
    async_session.add(foreign)
    await async_session.commit()
    actor_id, foreign_id = test_user.id, foreign.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    with patch("src.domains.agents.tools.application_notification_tools.get_db_context", session):
        runtime = make_tool_runtime(user_id=actor_id, store=InMemoryStore())
        read = await get_lia_notification_devices_tool.coroutine(
            query={"device_id": str(foreign_id)}, runtime=runtime
        )
        proposal = await remove_lia_notification_device_tool.coroutine(
            change={"device_id": str(foreign_id)}, runtime=runtime
        )
    assert read.success and read.structured_data["devices"] == []
    assert read.structured_data["total"] == 0
    assert not proposal.success and proposal.error_code == "NOT_FOUND"
    with pytest.raises(ResourceNotFoundError):
        await delete_token_by_id(str(foreign_id), test_user, async_session)
    assert (
        await async_session.scalar(select(UserFCMToken.id).where(UserFCMToken.id == foreign_id))
        == foreign_id
    )


@pytest.fixture(autouse=True)
def device_owner():
    previous = configure_notification_devices(SavedNotificationDevices())
    try:
        yield
    finally:
        configure_notification_devices(previous)


@pytest.mark.parametrize("intervention", ["none", "rotated", "removed", "platform_off"])
async def test_only_the_current_confirmed_registration_can_be_removed(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    row = UserFCMToken(
        id=uuid4(),
        user_id=test_user.id,
        token="private-push-credential",
        device_type="web",
        device_name="Saved browser",
        is_active=True,
    )
    async_session.add(row)
    await async_session.commit()
    await async_session.refresh(row)
    actor_id, row_id = test_user.id, row.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    queue = asyncio.Queue()
    with (
        patch("src.domains.agents.tools.application_notification_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
        installed_runtime_context(
            user_id=actor_id, language="fr", deps=object(), side_channel_queue=queue
        ),
    ):
        runtime = make_tool_runtime(user_id=actor_id, store=InMemoryStore(), language="fr")
        cards = await get_lia_notification_devices_tool.coroutine(runtime=runtime)
        assert cards.success and cards.structured_data["devices"][0]["id"] == str(row_id)
        assert "private-push-credential" not in str(cards) and "token_digest" not in str(
            cards.structured_data
        )
        proposal = await remove_lia_notification_device_tool.coroutine(
            change={"device_id": str(row_id)}, runtime=runtime
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        assert (
            await async_session.scalar(select(UserFCMToken.id).where(UserFCMToken.id == row_id))
            == row_id
        )
        item = next(iter(proposal.registry_updates.values()))
        draft_executor.register_executor("application_action", execute_application_action_draft)
        if intervention == "rotated":
            row.token = "rotated-private-credential"
            await async_session.commit()
        if intervention == "removed":
            await async_session.delete(row)
            await async_session.commit()
        if intervention == "platform_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        outcome = await draft_executor._execute_confirmed_draft(
            {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": item.payload["content"],
            },
            {"configurable": {"thread_id": "notification-confirmation"}},
            "notification-confirmation",
            "fr",
        )
    assert outcome.success is (intervention == "none")
    exists = await async_session.scalar(select(UserFCMToken.id).where(UserFCMToken.id == row_id))
    assert (exists is not None) is (intervention in {"rotated", "platform_off"})
    if intervention in {"rotated", "removed"}:
        assert draft_refusal_code(outcome) == "STALE_STATE"
    if intervention == "platform_off":
        assert draft_refusal_code(outcome) == "CAPABILITY_DISABLED"
        ledger.claim.assert_not_awaited()
    hints = [queue.get_nowait() for _ in range(queue.qsize())]
    hints = [event for event in hints if event.type == "application_state_changed"]
    assert len(hints) == int(intervention == "none")
    if hints:
        assert hints[0].metadata["change"]["resources"] == ["notification_devices"]
        assert str(row_id) not in str(hints[0].metadata)


async def test_device_editor_replaces_the_pending_target_without_exposing_delivery_credentials(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    rows = [
        UserFCMToken(
            id=uuid4(),
            user_id=test_user.id,
            token=f"private-token-{number}",
            device_type="web",
            device_name=f"Browser {number}",
            is_active=True,
        )
        for number in range(2)
    ]
    async_session.add_all(rows)
    await async_session.commit()
    actor_id, first_id, second_id = test_user.id, rows[0].id, rows[1].id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=AIMessage(
            content=json.dumps(
                {
                    "intent": {"device_id": str(second_id)},
                    "remove_fields": [],
                }
            )
        )
    )
    with (
        installed_runtime_context(user_id=actor_id, language="fr"),
        patch("src.domains.agents.tools.application_notification_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
        patch("src.domains.agents.services.hitl.draft_modifier.get_llm", return_value=llm),
    ):
        proposal = await remove_lia_notification_device_tool.coroutine(
            change={"device_id": str(first_id)},
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        item = next(iter(proposal.registry_updates.values()))
        original = ApplicationActionDraftContent.model_validate(item.payload["content"])
        revised_data = await DraftModificationService().modify(
            original.model_dump(mode="json"),
            f"Retire plutôt l'appareil {second_id}",
            "application_action",
            user_language="fr",
            run_id=item.id,
        )
    revised = ApplicationActionDraftContent.model_validate(revised_data)
    assert revised.intent["notification_device_to_remove"]["id"] == str(second_id)
    command = await get_command(async_session, original.command_id, actor_id)
    assert command is not None and matches_command(command, revised, item.id)
    assert not matches_command(command, original, item.id)
    assert set(
        (
            await async_session.scalars(
                select(UserFCMToken.id).where(UserFCMToken.user_id == actor_id)
            )
        ).all()
    ) == {first_id, second_id}
    prompt = str(llm.ainvoke.call_args.args[0])
    assert (
        "private-token" not in prompt
        and "token_digest" not in prompt
        and "updated_at" not in prompt
    )
