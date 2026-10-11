"""Native creation freezes the Studio intent and writes only after exact HITL."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from langgraph.store.memory import InMemoryStore
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
from src.domains.agents.application.routine_create_schemas import RoutineCreateRequest
from src.domains.agents.application.routine_creation import (
    execute_routine_creation,
    prepare_routine_creation,
)
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_routine_tools import create_lia_routine_tool
from src.domains.scheduled_actions.models import ScheduledAction
from src.domains.scheduled_actions.schemas import ScheduledActionCreate
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


async def test_native_condition_creation_is_proposal_only_until_its_confirmed_writer(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    content = await prepare_routine_creation(
        async_session,
        test_user.id,
        RoutineCreateRequest.model_validate(
            {
                "title": "Inbox",
                "action_prompt": "Summarize matching mail",
                "trigger_kind": "condition",
                "condition_config": {"type": "mail_match", "query": "receipt"},
                "requires_approval": True,
                "execution_mode": "pipeline",
            }
        ),
        command_id=uuid4(),
    )
    assert await async_session.get(ScheduledAction, content.command_id) is None
    receipt = PreferenceWriteReceipt()
    await execute_routine_creation(async_session, test_user.id, content, receipt)
    created = await async_session.get(ScheduledAction, content.command_id)
    assert receipt.committed and created is not None
    assert created.requires_approval is True and created.execution_mode == "pipeline"
    assert created.recurrence is None and created.condition_config["query"] == "receipt"


@pytest.mark.parametrize("condition", [False, True])
@pytest.mark.parametrize(
    "intervention", ["none", "off", "timezone", "limit", "writer_off", "commit_unknown"]
)
async def test_native_routine_creation_needs_exact_confirmation_and_a_current_mandate(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    condition: bool,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor_id = test_user.id
    request = (
        RoutineCreateRequest.model_validate(
            {
                "title": "Routine",
                "action_prompt": "Read the weather",
                "trigger_kind": "condition",
                "condition_config": {"type": "weather_change", "kinds": ["rain"]},
                "requires_approval": True,
                "execution_mode": "pipeline",
            }
        )
        if condition
        else RoutineCreateRequest(
            title="Routine",
            action_prompt="Read the weather",
            recurrence=RecurrenceSpec(
                freq="daily",
                times=DailyTimes(mode="at", at=(TimeOfDay(hour=9, minute=0),)),
                anchor_date=date(2026, 9, 1),
            ),
        )
    )

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except Exception:
            await async_session.rollback()
            raise

    if intervention in {"writer_off", "commit_unknown"}:
        original = ScheduledActionService.create

        async def withdraw_after_insert(
            service: ScheduledActionService,
            user_id: UUID,
            data: ScheduledActionCreate,
            user_timezone: str,
            *,
            action_id: UUID | None = None,
        ) -> ScheduledAction:
            result = await original(service, user_id, data, user_timezone, action_id=action_id)
            if intervention == "writer_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            else:
                original_commit = async_session.commit

                async def lost_ack() -> None:
                    await original_commit()
                    monkeypatch.setattr(async_session, "commit", original_commit)
                    raise SQLAlchemyError("simulated lost acknowledgement")

                monkeypatch.setattr(async_session, "commit", lost_ack)
            return result

        monkeypatch.setattr(ScheduledActionService, "create", withdraw_after_insert)
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
        proposal = await create_lia_routine_tool.coroutine(
            configuration=request,
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        content = item.payload["content"]
        assert (
            len(
                render_application_preview(
                    content, DRAFT_PREVIEW_LABELS["fr"], lambda value: value or ""
                )
            )
            == 3
        )
        identity = UUID(content["command_id"])
        assert await async_session.get(ScheduledAction, identity) is None
        with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
            await execute_application_action_draft(content, actor_id, object())
        if intervention == "off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif intervention == "timezone":
            test_user.timezone = "UTC" if test_user.timezone != "UTC" else "Europe/Paris"
            await async_session.commit()
        elif intervention == "limit":
            monkeypatch.setattr(
                "src.domains.scheduled_actions.service.SCHEDULED_ACTIONS_MAX_PER_USER", 0
            )
        draft_executor.register_executor("application_action", execute_application_action_draft)
        result = await draft_executor._execute_confirmed_draft(
            {"draft_id": item.id, "draft_type": "application_action", "draft_content": content},
            {"configurable": {"thread_id": "routine-creation"}},
            "routine-creation",
            "fr",
        )
    assert result.success is (intervention == "none")
    created = await async_session.get(ScheduledAction, identity)
    assert (created is not None) is (intervention in {"none", "commit_unknown"})
    if created:
        assert created.trigger_kind == ("condition" if condition else "time")
        assert created.requires_approval is condition
    if intervention == "limit":
        assert result.error == "CONSTRAINT_VIOLATION"
    if intervention == "timezone":
        assert result.error == "STALE_STATE"
    if intervention == "commit_unknown":
        assert result.error == "COMPLETION_UNKNOWN"


@pytest.mark.parametrize("enabled", [True, False])
async def test_legacy_creation_obeys_the_platform_tools_switch(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
) -> None:
    from src.domains.agents.tools.automation_tools import create_scheduled_action_tool

    monkeypatch.setattr(settings, "application_tools_enabled", enabled)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    with (
        installed_runtime_context(user_id=test_user.id, language="fr"),
        patch("src.domains.agents.tools.automation_tools.get_db_context", session),
    ):
        result = await create_scheduled_action_tool.coroutine(
            title="Daily",
            action_prompt="Read weather",
            repeat="daily",
            times=["09:00"],
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore()),
            locale="fr",
        )
    assert result.success is enabled
    if enabled:
        assert result.metadata["requires_confirmation"]
    else:
        assert result.error_code == "CAPABILITY_DISABLED"


@pytest.mark.parametrize("injected", [False, True])
async def test_creation_edit_replaces_approval_without_creating_a_routine(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    injected: bool,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    request = RoutineCreateRequest.model_validate(
        {
            "title": "Watch",
            "action_prompt": "Read tasks",
            "trigger_kind": "condition",
            "condition_config": {"type": "task_overdue"},
        }
    )

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    with (
        installed_runtime_context(user_id=test_user.id, language="fr"),
        patch("src.domains.agents.tools.application_routine_tools.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
    ):
        proposal = await create_lia_routine_tool.coroutine(
            configuration=request,
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore()),
        )
        item = next(iter(proposal.registry_updates.values()))
        original = ApplicationActionDraftContent.model_validate(item.payload["content"])
        intent = request.model_dump(mode="json")
        intent["title"] = "Revised watch"
        if injected:
            intent["user_timezone"] = "UTC"
            with pytest.raises(CommandRejected, match="INVALID_INPUT"):
                await rebuild_application_draft(item.payload["content"], {"intent": intent})
        else:
            revised = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(item.payload["content"], {"intent": intent})
            )
            assert revised.command_id == original.command_id
            saved = await get_command(async_session, revised.command_id, test_user.id)
            assert saved is not None and matches_command(saved, revised, item.id)
            assert not matches_command(saved, original, item.id)
        assert await async_session.get(ScheduledAction, original.command_id) is None
