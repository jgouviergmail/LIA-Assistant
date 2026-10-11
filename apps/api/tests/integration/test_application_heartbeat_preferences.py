"""Real command persistence and domain CAS; effect-ledger outcomes use a controlled double."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_repository import (
    get_command,
    matches_command,
    save_command,
)
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.heartbeat_operations import prepare_heartbeat_content
from src.domains.agents.application.heartbeat_schemas import HeartbeatPreferencePatch
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.services.hitl.draft_modifier import DraftModificationService
from src.domains.heartbeat import delivery_guard
from src.domains.heartbeat.preference_commands import update_heartbeat_preferences
from src.domains.heartbeat.schemas import HeartbeatSettingsUpdate
from src.domains.users.models import User
from tests.helpers.application_pending_proposal import pending_proposal
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration


async def test_edit_rebuilds_hours_and_refusals_without_writing_the_account(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    test_user.heartbeat_disabled_sources = []
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=AIMessage(
            content='{"intent":{"heartbeat_disabled_sources":["emails"],"heartbeat_notify_start_hour":22,"heartbeat_notify_end_hour":6},"remove_fields":[]}'
        )
    )
    with (
        installed_runtime_context(user_id=test_user.id, language="fr"),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
        patch("src.domains.agents.services.hitl.draft_modifier.get_llm", return_value=llm),
    ):
        old = await prepare_heartbeat_content(
            async_session,
            test_user.id,
            HeartbeatPreferencePatch(heartbeat_disabled_sources=["calendar"]),
        )
        draft_id = "draft-" + str(old.command_id)
        await save_command(async_session, old, draft_id)
        modified = await DraftModificationService().modify(
            old.model_dump(mode="json"),
            "Refuse les emails et notifie entre 22 h et 6 h",
            "application_action",
            user_language="fr",
            run_id=draft_id,
        )
    revised = ApplicationActionDraftContent.model_validate(modified)
    assert revised.after == {
        "heartbeat_disabled_sources": ["emails"],
        "heartbeat_notify_start_hour": 22,
        "heartbeat_notify_end_hour": 6,
    }
    await async_session.refresh(test_user)
    assert test_user.heartbeat_disabled_sources == []
    row = await get_command(async_session, old.command_id, test_user.id)
    assert row is not None and matches_command(row, revised, draft_id)
    assert not matches_command(row, old, draft_id)


@pytest.mark.parametrize("manual_intervention", [False, True])
async def test_exact_heartbeat_confirmation_and_newer_ui_changes(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    manual_intervention: bool,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    test_user.heartbeat_enabled = True
    test_user.heartbeat_disabled_sources = []
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    queue = asyncio.Queue()
    with (
        patch("src.domains.agents.tools.application_heartbeat_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
        installed_runtime_context(
            user_id=test_user.id, deps=object(), language="fr", side_channel_queue=queue
        ),
    ):
        output = await pending_proposal(
            async_session,
            test_user.id,
            HeartbeatPreferencePatch.model_validate(
                {"heartbeat_enabled": False, "heartbeat_disabled_sources": ["emails"]}
            ),
            "update_lia_heartbeat_preferences_tool",
            prepare_heartbeat_content,
        )
        assert output.success and output.metadata["requires_confirmation"]
        await async_session.refresh(test_user)
        assert test_user.heartbeat_enabled and test_user.heartbeat_disabled_sources == []
        assert queue.empty()
        item = next(iter(output.registry_updates.values()))
        if manual_intervention:
            await update_heartbeat_preferences(
                async_session,
                test_user.id,
                HeartbeatSettingsUpdate(heartbeat_disabled_sources=["calendar"]),
            )
        draft_executor.register_executor("application_action", execute_application_action_draft)
        result = await draft_executor._execute_confirmed_draft(
            {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": item.payload["content"],
            },
            {"configurable": {"thread_id": "heartbeat-confirmation"}},
            "heartbeat-confirmation",
            "fr",
        )
    await async_session.refresh(test_user)
    assert result.success is (not manual_intervention)
    assert test_user.heartbeat_enabled is manual_intervention
    assert test_user.heartbeat_disabled_sources == (
        ["calendar"] if manual_intervention else ["emails"]
    )
    if manual_intervention:
        assert result.error == "STALE_STATE"
    hints = [queue.get_nowait() for _ in range(queue.qsize())]
    hints = [event for event in hints if event.type == "application_state_changed"]
    assert len(hints) == int(not manual_intervention)
    if hints:
        assert hints[0].metadata["change"]["resources"] == ["heartbeat"]
        assert set(hints[0].metadata["change"]["changed_fields"]) == {
            "heartbeat_enabled",
            "heartbeat_disabled_sources",
        }


async def test_delivery_stamp_rereads_a_committed_opt_out(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "heartbeat_enabled", True)
    clock = Mock(wraps=datetime)
    clock.now.return_value = datetime(2026, 10, 7, 12, tzinfo=UTC)
    monkeypatch.setattr(delivery_guard, "datetime", clock)
    test_user.heartbeat_enabled = True
    test_user.timezone = "UTC"
    test_user.heartbeat_notify_start_hour, test_user.heartbeat_notify_end_hour = 8, 22
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    before = await delivery_guard.heartbeat_delivery_stamp(test_user.id)
    assert before is not None
    await update_heartbeat_preferences(
        async_session, test_user.id, HeartbeatSettingsUpdate(heartbeat_enabled=False)
    )
    assert await delivery_guard.heartbeat_delivery_current(test_user.id, before) is False
