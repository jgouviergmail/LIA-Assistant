"""Studio edits retain exact configuration and the source clock's consequences."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.core.i18n_drafts import DRAFT_PREVIEW_LABELS
from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay
from src.domains.agents.application.command_repository import get_command, matches_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.routine_update import (
    execute_routine_update,
    prepare_routine_update,
)
from src.domains.agents.application.routine_update_schemas import RoutineUpdateRequest
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_routine_tools import update_lia_routine_tool
from src.domains.scheduled_actions.schemas import (
    ConditionConfig,
    ScheduledActionCreate,
    ScheduledActionUpdate,
)
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "edit", ["rename", "condition", "to_condition", "time", "paused", "completed", "noop", "stale"]
)
async def test_native_edit_matches_source_clock_and_never_writes_before_confirmation(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, edit: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    source = ScheduledActionService(async_session)
    row = await source.create(
        test_user.id,
        ScheduledActionCreate(
            title="Watch",
            action_prompt="Read tasks",
            trigger_kind="condition",
            condition_config=ConditionConfig(type="task_overdue"),
            requires_approval=True,
        ),
        "Europe/Paris",
    )
    if edit == "paused":
        row.is_enabled, row.status = False, "paused"
    elif edit == "completed":
        row.is_enabled, row.status = False, "completed"
    await async_session.commit()
    recurrence = RecurrenceSpec(
        freq="daily",
        times=DailyTimes(mode="at", at=(TimeOfDay(hour=9, minute=0),)),
        anchor_date=date(2026, 9, 1),
    )
    if edit == "to_condition":
        await source.update(
            row.id, test_user.id, ScheduledActionUpdate(trigger_kind="time", recurrence=recurrence)
        )
        await async_session.commit()
    if edit == "condition":
        row.condition_state = {"seen": ["old-private-fact"]}
        await async_session.commit()
    old_clock, old_kind = row.next_trigger_at, row.trigger_kind
    changes: dict[str, object] = {"title": "New title"}
    if edit in {"time", "paused", "completed"}:
        changes = {"trigger_kind": "time", "recurrence": recurrence.model_dump(mode="json")}
    elif edit in {"condition", "to_condition"}:
        changes = {
            "trigger_kind": "condition",
            "condition_config": {"type": "mail_match", "query": "receipt"},
            "requires_approval": False,
        }
    elif edit == "noop":
        changes = {"title": "Watch"}
    content = await prepare_routine_update(
        async_session,
        test_user.id,
        RoutineUpdateRequest.model_validate({"routine_id": str(row.id), "changes": changes}),
    )
    assert row.title == "Watch" and row.trigger_kind == old_kind
    assert content.after["routine_configuration"]["enabled"] is (edit != "paused")
    assert "configuration_digest" in str(content.intent)
    if edit == "stale":
        row.action_prompt = "Different instruction"
        await async_session.commit()
        with pytest.raises(ResourceConflictError):
            await execute_routine_update(
                async_session, test_user.id, content, PreferenceWriteReceipt()
            )
        return
    receipt = PreferenceWriteReceipt()
    await execute_routine_update(async_session, test_user.id, content, receipt)
    assert receipt.committed and receipt.no_op is (edit == "noop")
    assert row.is_enabled is (edit != "paused")
    if edit in {"time", "paused", "completed"}:
        assert row.trigger_kind == "time" and row.condition_config is None
        assert row.recurrence is not None and row.next_trigger_at is not None
    elif edit in {"condition", "to_condition"}:
        assert row.condition_config["query"] == "receipt" and not row.requires_approval
        assert row.recurrence is None and row.condition_state is None
    else:
        assert row.title == ("Watch" if edit == "noop" else "New title")
        assert row.next_trigger_at == old_clock


@pytest.mark.parametrize("intervention", ["none", "off", "writer_off", "configured", "noop"])
async def test_native_update_requires_exact_hitl_and_rolls_back_a_late_withdrawal(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, intervention: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    row = await ScheduledActionService(async_session).create(
        test_user.id,
        ScheduledActionCreate(
            title="Watch",
            action_prompt="Read tasks",
            trigger_kind="condition",
            condition_config=ConditionConfig(type="task_overdue"),
        ),
        "Europe/Paris",
    )
    await async_session.commit()
    actor_id, row_id = test_user.id, row.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except Exception:
            await async_session.rollback()
            raise

    if intervention == "writer_off":
        original = ScheduledActionService.update

        async def withdraw(
            service: ScheduledActionService,
            action_id: UUID,
            user_id: UUID,
            data: ScheduledActionUpdate,
        ):
            result = await original(service, action_id, user_id, data)
            monkeypatch.setattr(settings, "application_tools_enabled", False)
            return result

        monkeypatch.setattr(ScheduledActionService, "update", withdraw)
    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    queue: asyncio.Queue[object] = asyncio.Queue()
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
        new_title = "Watch" if intervention == "noop" else "New title"
        proposal = await update_lia_routine_tool.coroutine(
            change={"routine_id": str(row_id), "changes": {"title": new_title}},
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        content = item.payload["content"]
        for language in DRAFT_PREVIEW_LABELS:
            lines = render_application_preview(
                content, DRAFT_PREVIEW_LABELS[language], lambda value: value or ""
            )
            assert len(lines) == 4 and "configuration_digest" not in str(lines)
        assert "configuration_digest" not in str(
            build_application_edit_prompt(content, "Rename it")
        )
        with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
            await execute_application_action_draft(content, actor_id, object())
        if intervention == "configured":
            row.action_prompt = "Changed instruction"
        elif intervention == "off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        await async_session.commit()
        draft_executor.register_executor("application_action", execute_application_action_draft)
        outcome = await draft_executor._execute_confirmed_draft(
            {"draft_id": item.id, "draft_type": "application_action", "draft_content": content},
            {"configurable": {"thread_id": "routine-edit"}},
            "routine-edit",
            "fr",
        )
    assert outcome.success is (intervention in {"none", "noop"})
    assert "configuration_digest" not in str(outcome.to_agent_result())
    stored = await ScheduledActionService(async_session).get_with_ownership_check(row_id, actor_id)
    assert stored.title == ("New title" if intervention == "none" else "Watch")


@pytest.mark.parametrize("injected", [False, True])
async def test_native_editor_refreshes_the_configuration_without_accepting_comparison_data(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, injected: bool
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    row = await ScheduledActionService(async_session).create(
        test_user.id,
        ScheduledActionCreate(
            title="Watch",
            action_prompt="Read tasks",
            trigger_kind="condition",
            condition_config=ConditionConfig(type="task_overdue"),
        ),
        "Europe/Paris",
    )
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    with (
        installed_runtime_context(user_id=test_user.id, language="fr"),
        patch("src.domains.agents.tools.application_routine_tools.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
    ):
        proposal = await update_lia_routine_tool.coroutine(
            change={"routine_id": str(row.id), "changes": {"title": "New title"}},
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore()),
        )
        item = next(iter(proposal.registry_updates.values()))
        original = ApplicationActionDraftContent.model_validate(item.payload["content"])
        row.action_prompt = "Current instruction"
        await async_session.commit()
        intent = {"routine_id": str(row.id), "changes": {"title": "Revised title"}}
        if injected:
            intent["expected"] = {"configuration_digest": "a" * 64}
            with pytest.raises(CommandRejected, match="INVALID_INPUT"):
                await rebuild_application_draft(item.payload["content"], {"intent": intent})
        else:
            revised = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(item.payload["content"], {"intent": intent})
            )
            saved = await get_command(async_session, revised.command_id, test_user.id)
            assert saved is not None and matches_command(saved, revised, item.id)
            assert not matches_command(saved, original, item.id)
            assert (
                revised.before["routine_configuration"]["configuration"]["action_prompt"]
                == "Current instruction"
            )
        assert row.title == "Watch"
