"""Channel commands preserve current ownership and exact snapshots on real PostgreSQL."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_channel_tools import (
    unlink_lia_channel_binding_tool,
    update_lia_channel_binding_tool,
)
from src.domains.channels.models import UserChannelBinding
from src.domains.channels.preference_commands import (
    channel_binding_snapshot,
    set_channel_binding_state,
    unlink_owned_channel_binding,
)
from src.domains.channels.service import ChannelService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("manual_intervention", [False, True])
@pytest.mark.parametrize("remove", [False, True])
async def test_native_channel_confirmation_uses_current_visible_identity_and_publishes_only_commit(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    manual_intervention: bool,
    remove: bool,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "channels_enabled", True)
    binding = UserChannelBinding(
        id=uuid4(),
        user_id=test_user.id,
        channel_type="telegram",
        channel_user_id=str(uuid4()),
        channel_username="@reader",
        is_active=True,
    )
    async_session.add(binding)
    await async_session.commit()
    binding_id = binding.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    queue = asyncio.Queue()
    with (
        patch("src.domains.agents.tools.application_channel_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
        installed_runtime_context(
            user_id=test_user.id, language="fr", deps=object(), side_channel_queue=queue
        ),
    ):
        runtime = make_tool_runtime(user_id=test_user.id, store=InMemoryStore(), language="fr")
        if remove:
            result = await unlink_lia_channel_binding_tool.coroutine(
                binding={"binding_id": str(binding.id)},
                runtime=runtime,
            )
        else:
            result = await update_lia_channel_binding_tool.coroutine(
                change={"binding_id": str(binding.id), "enabled": False},
                runtime=runtime,
            )
        assert result.success and result.metadata["requires_confirmation"]
        await async_session.refresh(binding)
        assert binding.is_active
        assert queue.empty()
        item = next(iter(result.registry_updates.values()))
        if manual_intervention:
            binding.channel_username = "@new-visible-name"
            await async_session.commit()
        draft_executor.register_executor("application_action", execute_application_action_draft)
        outcome = await draft_executor._execute_confirmed_draft(
            {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": item.payload["content"],
            },
            {"configurable": {"thread_id": "channel-confirmation"}},
            "channel-confirmation",
            "fr",
        )
    assert outcome.success is (not manual_intervention)
    saved = await async_session.get(UserChannelBinding, binding_id, populate_existing=True)
    if remove and not manual_intervention:
        assert saved is None
        assert outcome.result_data is not None
        assert outcome.result_data["values"] == {"channel_binding": None}
    else:
        assert saved is not None and saved.is_active is (manual_intervention or remove)
    if manual_intervention:
        assert outcome.error == "STALE_STATE"
    hints = [queue.get_nowait() for _ in range(queue.qsize())]
    hints = [event for event in hints if event.type == "application_state_changed"]
    assert len(hints) == int(not manual_intervention)
    if hints:
        assert hints[0].metadata["change"]["resources"] == ["channels"]
        assert hints[0].metadata["change"]["changed_fields"] == ["channel_binding"]


async def test_http_toggle_and_desired_state_share_the_same_saved_binding(
    async_session: AsyncSession, test_user: User
) -> None:
    actor_id = test_user.id
    binding = UserChannelBinding(
        id=uuid4(),
        user_id=test_user.id,
        channel_type="telegram",
        channel_user_id=str(uuid4()),
        channel_username="@reader",
        is_active=True,
    )
    async_session.add(binding)
    await async_session.commit()
    approved = channel_binding_snapshot(binding)
    binding_id = binding.id
    await ChannelService(async_session).toggle_binding(binding.id, test_user.id)
    await async_session.refresh(binding)
    assert not binding.is_active
    with pytest.raises(ResourceConflictError):
        await set_channel_binding_state(
            async_session, test_user.id, binding.id, False, expected=approved
        )
    await async_session.rollback()
    await async_session.refresh(binding)
    current = channel_binding_snapshot(binding)
    receipt = PreferenceWriteReceipt()
    await set_channel_binding_state(
        async_session, actor_id, binding_id, False, expected=current, receipt=receipt
    )
    assert receipt.committed and receipt.no_op


async def test_unlink_refuses_a_foreign_owner_then_removes_only_the_approved_binding(
    async_session: AsyncSession, test_user: User, test_superuser: User
) -> None:
    actor_id = test_user.id
    binding = UserChannelBinding(
        id=uuid4(),
        user_id=test_user.id,
        channel_type="telegram",
        channel_user_id=str(uuid4()),
        channel_username="@reader",
        is_active=True,
    )
    async_session.add(binding)
    await async_session.commit()
    binding_id = binding.id
    before = channel_binding_snapshot(binding)
    with pytest.raises(ResourceNotFoundError):
        await unlink_owned_channel_binding(
            async_session, test_superuser.id, binding_id, expected=before
        )
    await async_session.rollback()
    assert await async_session.get(UserChannelBinding, binding_id) is not None
    receipt = PreferenceWriteReceipt()
    await unlink_owned_channel_binding(
        async_session, actor_id, binding_id, expected=before, receipt=receipt
    )
    assert receipt.committed
    assert await async_session.get(UserChannelBinding, binding_id) is None
