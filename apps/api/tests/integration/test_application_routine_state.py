"""Routine proposals make no write and compare configuration at the real writer."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay
from src.domains.agents.application.command_repository import get_command, matches_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.routine_operations import (
    execute_routine_state,
    prepare_routine_state,
)
from src.domains.agents.application.routine_schemas import RoutineStateRequest
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_routine_tools import set_lia_routine_state_tool
from src.domains.agents.tools.automation_tools import toggle_scheduled_action_tool
from src.domains.scheduled_actions.models import ScheduledAction, ScheduledActionStatus
from src.domains.scheduled_actions.schemas import ScheduledActionCreate
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("intervention", ["none", "same", "configured", "tick", "foreign", "off"])
async def test_routine_change_compares_configuration_and_preserves_running_reservation(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    source = ScheduledActionService(async_session)
    row = await source.create(
        test_user.id,
        ScheduledActionCreate(
            title="My routine",
            action_prompt="Read the weather",
            recurrence=RecurrenceSpec(
                freq="daily",
                times=DailyTimes(mode="at", at=(TimeOfDay(hour=9, minute=0),)),
                anchor_date=date(2026, 9, 1),
            ),
        ),
        "Europe/Paris",
    )
    await async_session.commit()
    desired = intervention == "same"
    content = await prepare_routine_state(
        async_session, test_user.id, RoutineStateRequest(routine_id=row.id, enabled=desired)
    )
    assert row.is_enabled is True
    assert "Read the weather" not in str(content.model_dump())
    if intervention == "configured":
        row.action_prompt = "Read private messages"
    elif intervention == "tick":
        row.status = ScheduledActionStatus.EXECUTING
        row.execution_count += 1
        row.last_executed_at = datetime.now(UTC)
    elif intervention == "off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    await async_session.commit()
    receipt = PreferenceWriteReceipt()
    if intervention == "configured":
        with pytest.raises(ResourceConflictError):
            await execute_routine_state(async_session, test_user.id, content, receipt)
    elif intervention == "foreign":
        with pytest.raises(ResourceNotFoundError):
            await prepare_routine_state(
                async_session, test_user.id, RoutineStateRequest(routine_id=uuid4(), enabled=False)
            )
    elif intervention == "off":
        from src.core.exceptions import AuthorizationError

        with pytest.raises(AuthorizationError):
            await execute_routine_state(async_session, test_user.id, content, receipt)
    else:
        await execute_routine_state(async_session, test_user.id, content, receipt)
        await async_session.refresh(row)
        assert row.is_enabled is desired
        assert receipt.committed is True
        assert receipt.no_op is (intervention == "same")
        if intervention == "tick":
            assert row.status == ScheduledActionStatus.EXECUTING


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize(
    "intervention", ["none", "configured", "off", "inactive", "writer_off", "deleted"]
)
async def test_real_routine_tool_requires_exact_hitl_and_rechecks_current_authority(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    legacy: bool,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    source = ScheduledActionService(async_session)
    row = await source.create(
        test_user.id,
        ScheduledActionCreate(
            title="Routine",
            action_prompt="Read the weather",
            recurrence=RecurrenceSpec(
                freq="daily",
                times=DailyTimes(mode="at", at=(TimeOfDay(hour=9, minute=0),)),
                anchor_date=date(2026, 9, 1),
            ),
        ),
        "Europe/Paris",
    )
    await async_session.commit()
    actor_id = test_user.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except Exception:
            await async_session.rollback()
            raise

    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    queue: asyncio.Queue[object] = asyncio.Queue()
    if intervention == "writer_off":
        original = ScheduledActionService.set_enabled

        async def withdraw_after_source_write(
            service: ScheduledActionService, action_id: UUID, user_id: UUID, enabled: bool
        ) -> ScheduledAction:
            result = await original(service, action_id, user_id, enabled)
            monkeypatch.setattr(settings, "application_tools_enabled", False)
            return result

        monkeypatch.setattr(ScheduledActionService, "set_enabled", withdraw_after_source_write)
    with (
        installed_runtime_context(
            user_id=actor_id, language="fr", deps=object(), side_channel_queue=queue
        ),
        patch("src.domains.agents.tools.application_routine_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
    ):
        runtime = make_tool_runtime(user_id=actor_id, store=InMemoryStore())
        proposal = (
            await toggle_scheduled_action_tool.coroutine(
                action_id=str(row.id), runtime=runtime, locale="fr"
            )
            if legacy
            else await set_lia_routine_state_tool.coroutine(
                change={"routine_id": str(row.id), "enabled": False}, runtime=runtime
            )
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        assert row.is_enabled is True
        item = next(iter(proposal.registry_updates.values()))
        content = item.payload["content"]
        with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
            await execute_application_action_draft(content, actor_id, object())
        if intervention == "configured":
            row.requires_approval = not row.requires_approval
        elif intervention == "off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif intervention == "inactive":
            test_user.is_active = False
        elif intervention == "deleted":
            await source.delete(row.id, actor_id)
        await async_session.commit()
        draft_executor.register_executor("application_action", execute_application_action_draft)
        result = await draft_executor._execute_confirmed_draft(
            {"draft_id": item.id, "draft_type": "application_action", "draft_content": content},
            {"configurable": {"thread_id": "routine-confirmation"}},
            "routine-confirmation",
            "fr",
        )
    assert result.success is (intervention == "none")
    if intervention == "deleted":
        assert await async_session.get(ScheduledAction, row.id) is None
        assert result.error == "STALE_STATE"
    else:
        await async_session.refresh(row)
        assert row.is_enabled is (intervention != "none")
    assert "configuration_digest" not in str(result.to_agent_result())
    events = [queue.get_nowait() for _ in range(queue.qsize())]
    events = [event for event in events if event.type == "application_state_changed"]
    assert len(events) == int(intervention == "none")
    if events:
        assert events[0].metadata["change"]["resources"] == ["routines"]
        assert events[0].metadata["change"]["changed_fields"] == ["routine_state"]


@pytest.mark.parametrize("invalid", [False, True])
async def test_routine_editor_replaces_the_pending_digest_and_never_changes_state(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    invalid: bool,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    row = await ScheduledActionService(async_session).create(
        test_user.id,
        ScheduledActionCreate(
            title="Routine",
            action_prompt="Read the weather",
            recurrence=RecurrenceSpec(
                freq="daily",
                times=DailyTimes(mode="at", at=(TimeOfDay(hour=9, minute=0),)),
                anchor_date=date(2026, 9, 1),
            ),
        ),
        "Europe/Paris",
    )
    await async_session.commit()
    actor_id = test_user.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    with (
        installed_runtime_context(user_id=actor_id, language="fr"),
        patch("src.domains.agents.tools.application_routine_tools.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
    ):
        proposal = await set_lia_routine_state_tool.coroutine(
            change={"routine_id": str(row.id), "enabled": False},
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        item = next(iter(proposal.registry_updates.values()))
        original = ApplicationActionDraftContent.model_validate(item.payload["content"])
        intent = {"routine_id": str(row.id), "enabled": True}
        if invalid:
            intent["owner_id"] = "foreign"
            with pytest.raises(CommandRejected, match="INVALID_INPUT"):
                await rebuild_application_draft(item.payload["content"], {"intent": intent})
        else:
            revised = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(item.payload["content"], {"intent": intent})
            )
            saved = await get_command(async_session, revised.command_id, actor_id)
            assert saved is not None and matches_command(saved, revised, item.id)
            assert not matches_command(saved, original, item.id)
            assert revised.command_id == original.command_id
            assert revised.intent["routine_state"]["enabled"] is True
        await async_session.refresh(row)
        assert row.is_enabled is True
