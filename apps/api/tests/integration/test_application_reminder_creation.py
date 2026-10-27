"""Creation freezes the exact source clock and refuses stale authority before commit."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay
from src.domains.agents.application.command_repository import get_command, matches_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.reminder_create_schemas import ReminderCreateRequest
from src.domains.agents.application.reminder_creation import (
    execute_reminder_creation,
    prepare_reminder_creation,
)
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_reminder_tools import create_lia_reminder_tool
from src.domains.agents.tools.reminder_tools import create_reminder_tool
from src.domains.reminders.models import Reminder
from src.domains.reminders.schemas import ReminderCreate
from src.domains.reminders.service import ReminderService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.helpers.draft_refusals import draft_refusal_code
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
async def test_all_creation_entries_are_proposals_and_obey_the_global_switch(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    legacy: bool,
    enabled: bool,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", enabled)
    actor_id = test_user.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    with (
        installed_runtime_context(user_id=actor_id, language="fr"),
        patch("src.infrastructure.database.session.get_db_context", session),
        patch("src.domains.agents.tools.application_reminder_tools.get_db_context", session),
    ):
        runtime = make_tool_runtime(user_id=actor_id, store=InMemoryStore())
        instant = datetime.now(UTC) + timedelta(days=2)
        result = (
            await create_reminder_tool.coroutine(
                content="Remember",
                original_message="Remember",
                trigger_datetime=instant.isoformat(),
                runtime=runtime,
                locale="fr",
            )
            if legacy
            else await create_lia_reminder_tool.coroutine(
                configuration=ReminderCreateRequest(
                    content="Remember", original_message="Remember", trigger_at=instant
                ),
                runtime=runtime,
            )
        )
    assert result.success is enabled
    assert (
        await async_session.scalar(
            select(func.count()).select_from(Reminder).where(Reminder.user_id == actor_id)
        )
        == 0
    )
    if enabled:
        assert result.metadata["requires_confirmation"]
    else:
        assert result.error_code == "CAPABILITY_DISABLED"


@pytest.mark.parametrize("intervention", ["none", "writer_off", "commit_unknown"])
async def test_native_creation_requires_exact_hitl_and_commits_once(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, intervention: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor_id = test_user.id

    if intervention != "none":
        source_create = ReminderService.create_reminder

        async def alter_after_insert(
            service: ReminderService,
            owner_id: UUID,
            data: ReminderCreate,
            timezone: str,
            *,
            reminder_id: UUID | None = None,
        ) -> Reminder:
            created = await source_create(
                service, owner_id, data, timezone, reminder_id=reminder_id
            )
            if intervention == "writer_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            else:
                source_commit = async_session.commit

                async def lose_ack() -> None:
                    await source_commit()
                    monkeypatch.setattr(async_session, "commit", source_commit)
                    raise SQLAlchemyError("simulated lost commit acknowledgement")

                monkeypatch.setattr(async_session, "commit", lose_ack)
            return created

        monkeypatch.setattr(ReminderService, "create_reminder", alter_after_insert)

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
    with (
        installed_runtime_context(
            user_id=actor_id, language="fr", deps=object(), side_channel_queue=queue
        ),
        patch("src.domains.agents.tools.application_reminder_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
    ):
        proposal = await create_lia_reminder_tool.coroutine(
            configuration=ReminderCreateRequest(
                content="Remember",
                original_message="Private wording",
                trigger_at=datetime.now(UTC) + timedelta(days=2),
            ),
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        content = item.payload["content"]
        identity = UUID(content["command_id"])
        with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
            await execute_application_action_draft(content, actor_id, object())
        assert await async_session.get(Reminder, identity) is None
        draft_executor.register_executor("application_action", execute_application_action_draft)
        result = await draft_executor._execute_confirmed_draft(
            {"draft_id": item.id, "draft_type": "application_action", "draft_content": content},
            {"configurable": {"thread_id": "reminder-creation"}},
            "reminder-creation",
            "fr",
        )
        assert result.success is (intervention == "none")
        assert (await async_session.get(Reminder, identity) is not None) is (
            intervention != "writer_off"
        )
        if intervention == "commit_unknown":
            assert draft_refusal_code(result) == "COMPLETION_UNKNOWN"
        elif intervention == "writer_off":
            assert draft_refusal_code(result) == "CAPABILITY_DISABLED"
        assert "Private wording" not in str(result.result_data)
        events = [queue.get_nowait() for _ in range(queue.qsize())]
        changes = [event for event in events if event.type == "application_state_changed"]
        assert len(changes) == int(intervention == "none")
        if changes:
            assert changes[0].metadata["change"]["resources"] == ["reminders"]


async def test_native_reminder_creation_is_proposal_only_and_preserves_exact_seconds(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    requested = datetime.now(UTC) + timedelta(days=2, seconds=19)
    draft = await prepare_reminder_creation(
        async_session,
        test_user.id,
        ReminderCreateRequest(
            content="Remember", original_message="Remember", trigger_at=requested
        ),
    )
    assert await async_session.get(Reminder, draft.command_id) is None
    receipt = PreferenceWriteReceipt()
    await execute_reminder_creation(async_session, test_user.id, draft, receipt)
    persisted = await async_session.get(Reminder, draft.command_id)
    assert receipt.committed and persisted is not None
    assert persisted.trigger_at == requested and persisted.content == "Remember"


async def test_first_trigger_elapsing_during_the_source_write_is_not_committed(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor_id = test_user.id
    first = datetime.now(UTC) + timedelta(seconds=10)
    draft = await prepare_reminder_creation(
        async_session,
        actor_id,
        ReminderCreateRequest(content="Remember", original_message="Remember", trigger_at=first),
    )
    assert draft.expires_at > first + timedelta(seconds=1)
    source_create = ReminderService.create_reminder

    async def crosses_clock(
        service: ReminderService,
        owner_id: UUID,
        data: ReminderCreate,
        timezone: str,
        *,
        reminder_id: UUID | None = None,
    ) -> Reminder:
        result = await source_create(service, owner_id, data, timezone, reminder_id=reminder_id)
        replacement = AsyncMock()
        replacement.now = lambda zone: first + timedelta(seconds=1)
        monkeypatch.setattr(
            "src.domains.agents.application.reminder_creation.datetime", replacement
        )
        return result

    monkeypatch.setattr(ReminderService, "create_reminder", crosses_clock)
    receipt = PreferenceWriteReceipt()
    with pytest.raises(ResourceConflictError):
        await execute_reminder_creation(async_session, actor_id, draft, receipt)
    assert not receipt.committed
    await async_session.rollback()
    assert await async_session.get(Reminder, draft.command_id) is None


@pytest.mark.parametrize("withdrawal", ["timezone", "actor", "off"])
async def test_reminder_creation_refuses_changed_authority(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, withdrawal: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor_id = test_user.id
    draft = await prepare_reminder_creation(
        async_session,
        actor_id,
        ReminderCreateRequest(
            content="Remember",
            original_message="Remember",
            trigger_at=datetime.now(UTC) + timedelta(days=2),
        ),
    )
    if withdrawal == "timezone":
        test_user.timezone = "UTC" if test_user.timezone != "UTC" else "Europe/Paris"
        await async_session.commit()
    elif withdrawal == "actor":
        test_user.is_active = False
        await async_session.commit()
    else:
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    receipt = PreferenceWriteReceipt()
    with pytest.raises((AuthorizationError, ResourceConflictError)):
        await execute_reminder_creation(async_session, actor_id, draft, receipt)
    assert not receipt.committed and await async_session.get(Reminder, draft.command_id) is None


async def test_recurrence_crossing_its_confirmed_first_instant_requires_new_confirmation(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    test_user.timezone = "UTC"
    await async_session.commit()
    actor_id = test_user.id
    first = datetime(2099, 1, 15, 9, tzinfo=UTC)
    recurrence = RecurrenceSpec(
        freq="daily",
        anchor_date=first.date(),
        times=DailyTimes(mode="at", at=(TimeOfDay(hour=9, minute=0),)),
    )
    request = ReminderCreateRequest.model_validate(
        {
            "content": "Remember",
            "original_message": "Remember",
            "recurrence": recurrence.model_dump(mode="json"),
        }
    )
    with patch("src.domains.reminders.service.now_utc", return_value=first - timedelta(minutes=1)):
        draft = await prepare_reminder_creation(async_session, actor_id, request)
    receipt = PreferenceWriteReceipt()
    with (
        patch("src.domains.reminders.service.now_utc", return_value=first + timedelta(minutes=1)),
        pytest.raises(ResourceConflictError),
    ):
        await execute_reminder_creation(async_session, actor_id, draft, receipt)
    assert not receipt.committed and await async_session.get(Reminder, draft.command_id) is None


@pytest.mark.parametrize("injected", [False, True])
async def test_reminder_creation_edit_replaces_the_approval_and_never_creates_a_row(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, injected: bool
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor_id = test_user.id
    request = ReminderCreateRequest(
        content="Remember",
        original_message="Remember",
        trigger_at=datetime.now(UTC) + timedelta(days=2),
    )

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    with (
        installed_runtime_context(user_id=actor_id, language="fr"),
        patch("src.domains.agents.tools.application_reminder_tools.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
    ):
        output = await create_lia_reminder_tool.coroutine(
            configuration=request,
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        assert output.success
        item = next(iter(output.registry_updates.values()))
        original = ApplicationActionDraftContent.model_validate(item.payload["content"])
        intent = request.model_dump(mode="json")
        intent["content"] = "Revised content"
        if injected:
            intent["user_timezone"] = "UTC"
            with pytest.raises(CommandRejected, match="INVALID_INPUT"):
                await rebuild_application_draft(item.payload["content"], {"intent": intent})
        else:
            revised = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(item.payload["content"], {"intent": intent})
            )
            assert revised.command_id == original.command_id
            saved = await get_command(async_session, revised.command_id, actor_id)
            assert saved is not None and matches_command(saved, revised, item.id)
            assert not matches_command(saved, original, item.id)
        assert await async_session.get(Reminder, original.command_id) is None
