"""Real PostgreSQL and native dispatcher: preview, confirmation and conflict."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.preparation import prepare_preference_change
from src.domains.agents.application.schemas import PreferenceChangeRequest
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.users.models import User
from src.domains.users.schemas import UserUpdate
from src.domains.users.service import UserService
from tests.helpers.draft_refusals import draft_refusal_code
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("intervention", ["none", "manual", "capability", "inactive"])
async def test_native_confirmation_saves_only_the_exact_currently_approved_change(
    async_session: AsyncSession,
    test_user: User,
    intervention: str,
) -> None:
    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    state_queue = asyncio.Queue()
    with (
        patch("src.domains.agents.tools.application_action_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
        installed_runtime_context(
            user_id=test_user.id, deps=object(), language="fr", side_channel_queue=state_queue
        ),
    ):
        initial = test_user.font_size
        # Pending drafts issued before the reversible-setting policy remain executable.
        content = await prepare_preference_change(
            async_session, test_user.id, PreferenceChangeRequest(mode="increase_font")
        )
        output = DraftService().create_draft(
            draft_type=DraftType.APPLICATION_ACTION,
            content=content.model_dump(mode="json"),
            source_tool="update_lia_preferences_tool",
            user_language="fr",
        )
        await save_command(async_session, content, next(iter(output.registry_updates)))
        assert output.success and output.metadata["requires_confirmation"]
        await async_session.refresh(test_user)
        assert test_user.font_size == initial
        assert state_queue.empty()
        item = next(iter(output.registry_updates.values()))
        if intervention == "manual":
            await UserService(async_session).update_user(
                test_user.id, UserUpdate(font_size=initial + 2)
            )
        elif intervention == "capability":
            async_session.add(
                SystemSetting(
                    key=SystemSettingKey.CAPABILITY_APPLICATION_TOOLS_ENABLED, value="false"
                )
            )
            await async_session.commit()
        elif intervention == "inactive":
            test_user.is_active = False
            await async_session.commit()
        draft_executor.register_executor("application_action", execute_application_action_draft)
        result = await draft_executor._execute_confirmed_draft(
            {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": item.payload["content"],
            },
            {"configurable": {"thread_id": "test-conversation"}},
            "application-confirmation",
            "fr",
        )
    await async_session.refresh(test_user)
    assert (
        test_user.font_size
        == initial + {"none": 1, "manual": 2, "capability": 0, "inactive": 0}[intervention]
    )
    assert result.success is (intervention == "none")
    changes = [state_queue.get_nowait() for _ in range(state_queue.qsize())]
    assert sum(event.type == "application_state_changed" for event in changes) == int(
        intervention == "none"
    )
    if intervention == "none":
        assert result.result_data["committed"] is True
        assert result.result_data["values"] == {"font_size": initial + 1}
    else:
        assert (
            draft_refusal_code(result)
            == {
                "manual": "STALE_STATE",
                "capability": "CAPABILITY_DISABLED",
                "inactive": "FORBIDDEN",
            }[intervention]
        )
    if intervention in {"none", "manual"}:
        ledger.claim.assert_awaited_once()
        ledger.close.assert_awaited_once()
    else:
        ledger.claim.assert_not_awaited()


async def test_post_commit_failure_reports_saved_state_separately_from_propagation(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    state_queue = asyncio.Queue()
    target = "UTC" if test_user.timezone != "UTC" else "Europe/Paris"
    with (
        patch("src.domains.agents.tools.application_action_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch(
            "src.infrastructure.scheduler.timezone_propagation.propagate_timezone",
            new=AsyncMock(side_effect=RuntimeError("planted-secret-diagnostic")),
        ),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
        installed_runtime_context(
            user_id=test_user.id, deps=object(), side_channel_queue=state_queue
        ),
    ):
        content = await prepare_preference_change(
            async_session,
            test_user.id,
            PreferenceChangeRequest(mode="set", patch={"timezone": target}),
        )
        output = DraftService().create_draft(
            draft_type=DraftType.APPLICATION_ACTION,
            content=content.model_dump(mode="json"),
            source_tool="update_lia_preferences_tool",
            user_language="fr",
        )
        await save_command(async_session, content, next(iter(output.registry_updates)))
        assert output.success
        item = next(iter(output.registry_updates.values()))
        draft_executor.register_executor("application_action", execute_application_action_draft)
        result = await draft_executor._execute_confirmed_draft(
            {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": item.payload["content"],
            },
            {"configurable": {"thread_id": "test-conversation"}},
            "application-partial",
            "fr",
        )
    await async_session.refresh(test_user)
    assert test_user.timezone == target
    assert not result.success
    assert result.result_data["committed"] is True
    assert draft_refusal_code(result) == "POST_COMMIT_FAILURE"
    changes = [state_queue.get_nowait() for _ in range(state_queue.qsize())]
    change = next(event for event in changes if event.type == "application_state_changed")
    assert change.metadata["change"]["changed_fields"] == ["timezone"]
    assert "planted-secret" not in str(result.to_agent_result())
