"""A routine deletion compares the exact configuration and uses the source cascade."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.core.i18n_drafts import DRAFT_PREVIEW_LABELS
from src.domains.agents.application.command_repository import get_command, matches_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.routine_removal import (
    execute_routine_removal,
    prepare_routine_removal,
)
from src.domains.agents.application.routine_removal_schemas import RoutineDeleteRequest
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_routine_tools import delete_lia_routine_tool
from src.domains.scheduled_actions.models import (
    ScheduledAction,
    ScheduledActionRun,
    ScheduledRunOutcome,
)
from src.domains.scheduled_actions.run_repository import ScheduledActionRunRepository
from src.domains.scheduled_actions.schemas import ConditionConfig, ScheduledActionCreate
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("configured", [False, True])
async def test_routine_deletion_keeps_a_changed_target_and_never_deletes_at_preparation(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    configured: bool,
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
    content = await prepare_routine_removal(
        async_session, test_user.id, RoutineDeleteRequest(routine_id=row.id)
    )
    assert await async_session.get(ScheduledAction, row.id) is not None
    if configured:
        row.action_prompt = "Different instruction"
        await async_session.commit()
        with pytest.raises(ResourceConflictError):
            await execute_routine_removal(
                async_session, test_user.id, content, PreferenceWriteReceipt()
            )
    else:
        receipt = PreferenceWriteReceipt()
        await execute_routine_removal(async_session, test_user.id, content, receipt)
        assert receipt.committed
        assert await async_session.get(ScheduledAction, row.id) is None


@pytest.mark.parametrize("intervention", ["none", "configured", "off", "writer_off", "running"])
async def test_native_delete_requires_hitl_and_removes_only_the_approved_routine_history(
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
            title="Watch",
            action_prompt="Read tasks",
            trigger_kind="condition",
            condition_config=ConditionConfig(type="task_overdue"),
        ),
        "Europe/Paris",
    )
    now = datetime.now(UTC)
    run = await ScheduledActionRunRepository(async_session).record(
        scheduled_action_id=row.id,
        user_id=test_user.id,
        slot_at=now,
        started_at=now,
        ended_at=now,
        outcome=ScheduledRunOutcome.SUCCESS,
        attempts=1,
        manual=False,
    )
    await async_session.commit()
    row_id, run_id, actor_id = row.id, run.id, test_user.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except Exception:
            await async_session.rollback()
            raise

    if intervention == "writer_off":
        original = ScheduledActionService.delete

        async def withdraw_after_delete(
            service: ScheduledActionService, action_id: UUID, user_id: UUID
        ) -> None:
            await original(service, action_id, user_id)
            monkeypatch.setattr(settings, "application_tools_enabled", False)

        monkeypatch.setattr(ScheduledActionService, "delete", withdraw_after_delete)
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
        proposal = await delete_lia_routine_tool.coroutine(
            selection={"routine_id": str(row_id)},
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        content = item.payload["content"]
        lines = render_application_preview(
            content, DRAFT_PREVIEW_LABELS["fr"], lambda value: value or ""
        )
        assert len(lines) == 3 and "configuration_digest" not in str(lines)
        with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
            await execute_application_action_draft(content, actor_id, object())
        if intervention == "configured":
            row.action_prompt = "Changed"
        elif intervention == "off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif intervention == "running":
            row.status = "executing"
        await async_session.commit()
        draft_executor.register_executor("application_action", execute_application_action_draft)
        outcome = await draft_executor._execute_confirmed_draft(
            {"draft_id": item.id, "draft_type": "application_action", "draft_content": content},
            {"configurable": {"thread_id": "routine-deletion"}},
            "routine-deletion",
            "fr",
        )
    removed = intervention in {"none", "running"}
    assert outcome.success is removed
    assert "configuration_digest" not in str(outcome.to_agent_result())
    assert (
        await async_session.scalar(select(ScheduledAction.id).where(ScheduledAction.id == row_id))
        is None
    ) is removed
    assert (
        await async_session.scalar(
            select(ScheduledActionRun.id).where(ScheduledActionRun.id == run_id)
        )
        is None
    ) is removed


@pytest.mark.parametrize("injected", [False, True])
async def test_removal_edit_reloads_snapshot_and_cannot_inject_comparison_data(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    injected: bool,
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
        proposal = await delete_lia_routine_tool.coroutine(
            selection={"routine_id": str(row.id)},
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore()),
        )
        item = next(iter(proposal.registry_updates.values()))
        original = ApplicationActionDraftContent.model_validate(item.payload["content"])
        row.title = "New title"
        await async_session.commit()
        intent = {"routine_id": str(row.id)}
        if injected:
            intent["configuration_digest"] = "a" * 64
            with pytest.raises(CommandRejected, match="INVALID_INPUT"):
                await rebuild_application_draft(item.payload["content"], {"intent": intent})
        else:
            revised = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(item.payload["content"], {"intent": intent})
            )
            saved = await get_command(async_session, revised.command_id, test_user.id)
            assert saved is not None and matches_command(saved, revised, item.id)
            assert not matches_command(saved, original, item.id)
        assert await async_session.get(ScheduledAction, row.id) is not None
