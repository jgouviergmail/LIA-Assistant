"""Native launch prepares exact approval before reserving or scheduling work."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.i18n_drafts import DRAFT_PREVIEW_LABELS
from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay
from src.domains.agents.application.command_repository import get_command, matches_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.routine_execution import (
    _run_reserved,
    execute_routine_launch,
    prepare_routine_launch,
)
from src.domains.agents.application.routine_run_schemas import RoutineRunRequest
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_routine_tools import execute_lia_routine_tool
from src.domains.scheduled_actions.models import ScheduledAction, ScheduledActionRun
from src.domains.scheduled_actions.schemas import ConditionConfig, ScheduledActionCreate
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.scheduler.out_of_turn_run import RunOutcome, RunResult
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


async def test_native_manual_proposal_neither_reserves_nor_starts_work_before_approval(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    row = await ScheduledActionService(async_session).create(
        test_user.id,
        ScheduledActionCreate(
            title="Run",
            action_prompt="Read tasks",
            trigger_kind="condition",
            condition_config=ConditionConfig(type="task_overdue"),
        ),
        "Europe/Paris",
    )
    await async_session.commit()
    content = await prepare_routine_launch(
        async_session, test_user.id, RoutineRunRequest(routine_id=row.id)
    )
    assert row.status == "active" and row.execution_token is None
    receipt = PreferenceWriteReceipt()
    with (
        installed_runtime_context(user_id=test_user.id, language="fr"),
        patch(
            "src.domains.agents.application.routine_execution._start_reserved_run", Mock()
        ) as enqueue,
    ):
        await execute_routine_launch(async_session, test_user.id, content, receipt)
    assert (
        receipt.committed
        and row.status == "executing"
        and row.execution_token == content.command_id
    )
    enqueue.assert_called_once()


@pytest.mark.parametrize(
    "intervention",
    ["none", "off", "configured", "running", "writer_off", "enqueue_error", "commit_unknown"],
)
async def test_native_manual_trigger_needs_exact_hitl_and_reports_accepted_work_only(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, intervention: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    row = await ScheduledActionService(async_session).create(
        test_user.id,
        ScheduledActionCreate(
            title="Run",
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

    if intervention in {"writer_off", "commit_unknown"}:
        original = ScheduledActionService.reserve_manual_execution

        async def intervene(
            service: ScheduledActionService,
            action_id: UUID,
            user_id: UUID,
            *,
            execution_token: UUID | None = None,
        ) -> ScheduledAction:
            result = await original(service, action_id, user_id, execution_token=execution_token)
            if intervention == "writer_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            else:
                commit = async_session.commit

                async def lost_ack() -> None:
                    await commit()
                    monkeypatch.setattr(async_session, "commit", commit)
                    raise SQLAlchemyError("simulated lost reservation acknowledgement")

                monkeypatch.setattr(async_session, "commit", lost_ack)
            return result

        monkeypatch.setattr(ScheduledActionService, "reserve_manual_execution", intervene)
    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    queue: asyncio.Queue[object] = asyncio.Queue()
    enqueue = Mock(
        side_effect=RuntimeError("launch refused") if intervention == "enqueue_error" else None
    )
    with (
        installed_runtime_context(
            user_id=actor_id, language="fr", deps=object(), side_channel_queue=queue
        ),
        patch("src.domains.agents.tools.application_routine_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.agents.application.routine_execution._start_reserved_run", enqueue),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
    ):
        proposal = await execute_lia_routine_tool.coroutine(
            selection={"routine_id": str(row_id)},
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        content = item.payload["content"]
        assert row.status == "active" and row.execution_token is None

        for language in DRAFT_PREVIEW_LABELS:
            lines = render_application_preview(
                content, DRAFT_PREVIEW_LABELS[language], lambda value: value or ""
            )
            assert len(lines) == 4 and "configuration_digest" not in str(lines)
        assert "configuration_digest" not in str(
            build_application_edit_prompt(content, "Run this one")
        )
        with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
            await execute_application_action_draft(content, actor_id, object())
        if intervention == "off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif intervention == "configured":
            row.action_prompt = "Changed instruction"
        elif intervention == "running":
            await ScheduledActionService(async_session).reserve_manual_execution(row_id, actor_id)
        await async_session.commit()
        draft_executor.register_executor("application_action", execute_application_action_draft)
        outcome = await draft_executor._execute_confirmed_draft(
            {"draft_id": item.id, "draft_type": "application_action", "draft_content": content},
            {"configurable": {"thread_id": "manual-routine"}},
            "manual-routine",
            "fr",
        )
    assert outcome.success is (intervention == "none")
    assert enqueue.call_count == int(intervention in {"none", "enqueue_error"})
    if intervention == "none":
        values = outcome.result_data["values"]
        assert values["launch_reserved"] is True and values["execution_completed"] is False
        assert "consultez" in outcome.to_agent_result()["message"]
    elif intervention == "enqueue_error":
        assert outcome.result_data["committed"] is True
        assert outcome.result_data["error_code"] == "POST_COMMIT_FAILURE"
    elif intervention == "commit_unknown":
        assert outcome.result_data["error_code"] == "COMPLETION_UNKNOWN"
    stored = await ScheduledActionService(async_session).get_with_ownership_check(row_id, actor_id)
    assert (stored.status == "executing") is (
        intervention in {"none", "running", "enqueue_error", "commit_unknown"}
    )


@pytest.mark.parametrize("injected", [False, True])
async def test_launch_editor_rereads_current_instruction_without_accepting_a_new_instruction(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, injected: bool
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    row = await ScheduledActionService(async_session).create(
        test_user.id,
        ScheduledActionCreate(
            title="Run",
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
        proposal = await execute_lia_routine_tool.coroutine(
            selection={"routine_id": str(row.id)},
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore()),
        )
        item = next(iter(proposal.registry_updates.values()))
        original = ApplicationActionDraftContent.model_validate(item.payload["content"])
        row.action_prompt = "Current instruction"
        await async_session.commit()
        intent = {"routine_id": str(row.id)}
        if injected:
            intent["action_prompt"] = "Injected instruction"
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
                revised.after["routine_to_run"]["configuration"]["action_prompt"]
                == "Current instruction"
            )
        assert row.status == "active" and row.execution_token is None


@pytest.mark.parametrize("intervention", ["none", "quota", "changed"])
async def test_deferred_native_job_uses_the_real_source_worker_and_persists_its_result(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, intervention: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    row = await ScheduledActionService(async_session).create(
        test_user.id,
        ScheduledActionCreate(
            title="Run",
            action_prompt="Approved instruction",
            recurrence=RecurrenceSpec(
                freq="daily",
                times=DailyTimes(mode="at", at=(TimeOfDay(hour=9, minute=0),)),
                anchor_date=date(2026, 9, 1),
            ),
        ),
        "Europe/Paris",
    )
    await async_session.commit()
    actor_id, row_id = test_user.id, row.id
    content = await prepare_routine_launch(
        async_session, actor_id, RoutineRunRequest(routine_id=row_id)
    )

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except Exception:
            await async_session.rollback()
            raise

    with (
        installed_runtime_context(user_id=actor_id, language="fr"),
        patch(
            "src.domains.agents.application.routine_execution._start_reserved_run", Mock()
        ) as enqueue,
    ):
        await execute_routine_launch(async_session, actor_id, content, PreferenceWriteReceipt())
    reservation = enqueue.call_args.args[0]
    if intervention == "changed":
        row.action_prompt = "Unapproved instruction"
        await async_session.commit()
    generation = AsyncMock(
        return_value=RunResult(RunOutcome.SUCCESS, text="Simulated result", attempts=1)
    )
    with (
        patch("src.infrastructure.database.session.get_db_context", session),
        patch("src.domains.agents.application.routine_execution_policy.get_db_context", session),
        patch("src.domains.agents.application.routine_execution.get_redis_cache", AsyncMock()),
        patch(
            "src.domains.agents.application.routine_execution.wait_for_routine_turn",
            AsyncMock(return_value=True),
        ),
        patch(
            "src.domains.usage_limits.service.UsageLimitService.is_user_blocked_for_llm",
            AsyncMock(return_value=intervention == "quota"),
        ) as quota,
        patch(
            "src.infrastructure.scheduler.scheduled_action_executor.conversation_has_pending_hitl",
            AsyncMock(return_value=(False, None)),
        ),
        patch(
            "src.infrastructure.scheduler.scheduled_action_executor.stream_instruction", generation
        ),
        patch("src.infrastructure.scheduler.scheduled_action_executor._notify_result", AsyncMock()),
    ):
        await _run_reserved(reservation, "owned-conversation")
    assert generation.await_count == int(intervention == "none")
    quota.assert_awaited_once()
    await async_session.refresh(row)
    assert row.status == "active" and row.execution_token is None
    runs = list(
        (
            await async_session.scalars(
                select(ScheduledActionRun).where(ScheduledActionRun.scheduled_action_id == row_id)
            )
        ).all()
    )
    assert len(runs) == int(intervention == "none")
    if intervention == "none":
        assert generation.await_args.args[0].prompt == "Approved instruction"
        assert runs[0].outcome == "success" and runs[0].manual and row.execution_count == 1
