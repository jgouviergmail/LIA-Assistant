"""Confirmed Live provider changes use real SQL and a controlled provider probe."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langgraph.store.memory import InMemoryStore
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_repository import get_command, matches_command
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.services.hitl.draft_modifier import DraftModificationService
from src.domains.agents.tools.application_live_connector_tools import (
    update_lia_live_connector_settings_tool,
)
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.live.connector_preference_gateway import SavedLiveConnectorPreferences
from src.domains.live.connector_service import LiveConnectorService
from src.domains.live.model_settings import LiveModelSettings, write_models
from src.domains.live.preferences import LivePreferences
from src.domains.live.schemas import LiveConnectorSettings
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.users.models import User
from src.infrastructure.live_connector_preferences import configure_live_connector_preferences
from tests.helpers.draft_refusals import draft_refusal_code
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


async def test_operator_disable_while_waiting_for_user_lock_prevents_native_provider_work(
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from src.core.exceptions import AuthorizationError
    from src.domains.live.connector_preference_commands import connector_preference_snapshot
    from src.domains.users.preference_cas import PreferenceWriteReceipt

    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "live_enabled", True)
    test_user = User(
        id=uuid4(),
        email=f"live-lock-{uuid4()}@example.test",
        is_active=True,
        live_preferences=LivePreferences(provider="gemini").model_dump(),
    )
    connector = Connector(
        id=uuid4(),
        user_id=test_user.id,
        connector_type=ConnectorType.GEMINI_LIVE,
        status=ConnectorStatus.ACTIVE,
        scopes=[],
        credentials_encrypted="private-key",
        connector_metadata=write_models(
            {},
            "model",
            LiveModelSettings(voice="Kore", idle_timeout_seconds=60, session_max_minutes=10),
        ),
    )
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    async with maker() as setup:
        setup.add_all([test_user, connector])
        await setup.commit()
    expected = connector_preference_snapshot(test_user, connector, "gemini")
    actor_id = test_user.id
    probe, key = AsyncMock(), AsyncMock(return_value="private-key")
    starting = asyncio.Event()

    async def change() -> None:
        async with maker() as db:
            actor = await db.get(User, actor_id)
            assert actor is not None
            starting.set()
            await LiveConnectorService(db).update_connector_settings(
                actor,
                "gemini",
                LiveConnectorSettings(
                    model="model", voice="Puck", idle_timeout_seconds=60, session_max_minutes=10
                ),
                language="fr",
                expected=expected,
                receipt=PreferenceWriteReceipt(),
            )

    async with maker() as blocker:
        await blocker.scalar(select(User).where(User.id == actor_id).with_for_update())
        with (
            patch.object(LiveConnectorService, "api_key_of", key),
            patch.object(LiveConnectorService, "_check_choice", probe),
        ):
            changing = asyncio.create_task(change())
            try:
                await asyncio.wait_for(starting.wait(), timeout=5)
                await asyncio.sleep(0.05)
                assert not changing.done()
                async with maker() as operator:
                    current = await operator.scalar(
                        select(SystemSetting).where(
                            SystemSetting.key
                            == SystemSettingKey.CAPABILITY_APPLICATION_TOOLS_ENABLED
                        )
                    )
                    previous_value = current.value if current is not None else None
                    if current is None:
                        operator.add(
                            SystemSetting(
                                key=SystemSettingKey.CAPABILITY_APPLICATION_TOOLS_ENABLED,
                                value="false",
                            )
                        )
                    else:
                        current.value = "false"
                    await operator.commit()
                await blocker.rollback()
                with pytest.raises(AuthorizationError):
                    await asyncio.wait_for(changing, timeout=5)
                probe.assert_not_awaited()
                key.assert_not_awaited()
            finally:
                await blocker.rollback()
                await asyncio.gather(changing, return_exceptions=True)
                async with maker() as cleanup:
                    await cleanup.execute(delete(User).where(User.id == actor_id))
                    current = await cleanup.scalar(
                        select(SystemSetting).where(
                            SystemSetting.key
                            == SystemSettingKey.CAPABILITY_APPLICATION_TOOLS_ENABLED
                        )
                    )
                    if current is not None:
                        if previous_value is None:
                            await cleanup.delete(current)
                        else:
                            current.value = previous_value
                    await cleanup.commit()


@pytest.mark.parametrize(
    "intervention", ["none", "rotated", "platform_off", "live_off", "probe_refused"]
)
async def test_confirmed_live_connector_change_probes_only_the_exact_approved_current_state(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
) -> None:
    from src.domains.live.errors import LiveRefusedError

    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "live_enabled", True)
    test_user.live_preferences = LivePreferences(
        interruptions=False, provider="gemini"
    ).model_dump()
    connector = Connector(
        id=uuid4(),
        user_id=test_user.id,
        connector_type=ConnectorType.GEMINI_LIVE,
        status=ConnectorStatus.ACTIVE,
        scopes=[],
        credentials_encrypted="private-key",
        connector_metadata=write_models(
            {},
            "model",
            LiveModelSettings(voice="Kore", idle_timeout_seconds=60, session_max_minutes=10),
        ),
    )
    async_session.add(connector)
    await async_session.commit()
    actor_id = test_user.id
    previous = configure_live_connector_preferences(SavedLiveConnectorPreferences())
    probe = AsyncMock()
    if intervention == "probe_refused":
        probe.side_effect = LiveRefusedError(
            status_code=422, code="provider_refused", message="private-vendor-detail"
        )
    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    try:
        with (
            installed_runtime_context(user_id=actor_id, language="fr", deps=object()),
            patch(
                "src.domains.agents.tools.application_live_connector_tools.get_db_context", session
            ),
            patch("src.domains.agents.application.command_service.get_db_context", session),
            patch("src.domains.agents.application.draft_execution.get_db_context", session),
            patch("src.domains.agents.effects.runtime._LEDGER", ledger),
            patch.object(LiveConnectorService, "api_key_of", AsyncMock(return_value="key")),
            patch.object(LiveConnectorService, "_check_choice", probe),
            patch.dict(draft_executor.EXECUTOR_REGISTRY),
        ):
            proposal = await update_lia_live_connector_settings_tool.coroutine(
                change={"provider": "gemini", "settings": {"voice": "Puck"}},
                runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
            )
            assert proposal.success and proposal.metadata["requires_confirmation"]
            probe.assert_not_awaited()
            assert connector.connector_metadata["models"]["model"]["voice"] == "Kore"
            item = next(iter(proposal.registry_updates.values()))
            if intervention == "rotated":
                connector.credentials_encrypted = "rotated-key"
                await async_session.commit()
            if intervention == "platform_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            if intervention == "live_off":
                monkeypatch.setattr(settings, "live_enabled", False)
            draft_executor.register_executor("application_action", execute_application_action_draft)
            outcome = await draft_executor._execute_confirmed_draft(
                {
                    "draft_id": item.id,
                    "draft_type": "application_action",
                    "draft_content": item.payload["content"],
                },
                {"configurable": {"thread_id": "live-provider-confirmation"}},
                "live-provider-confirmation",
                "fr",
            )
        assert outcome.success is (intervention == "none")
        if intervention == "none":
            assert "stored_digest" not in str(outcome.to_agent_result())
        if intervention == "probe_refused":
            assert draft_refusal_code(outcome) == "EXTERNAL_API_ERROR"
        assert probe.await_count == int(intervention in {"none", "probe_refused"})
        await async_session.refresh(connector)
        assert connector.connector_metadata["models"]["model"]["voice"] == (
            "Puck" if intervention == "none" else "Kore"
        )
        assert "private-vendor-detail" not in str(outcome.to_dict())
    finally:
        configure_live_connector_preferences(previous)


async def test_live_provider_editor_replaces_exact_pending_state_without_probe_or_private_context(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "live_enabled", True)
    test_user.live_preferences = LivePreferences(provider="gemini").model_dump()
    connector = Connector(
        id=uuid4(),
        user_id=test_user.id,
        connector_type=ConnectorType.GEMINI_LIVE,
        status=ConnectorStatus.ACTIVE,
        scopes=[],
        credentials_encrypted="private-secret-key",
        connector_metadata=write_models(
            {},
            "model",
            LiveModelSettings(voice="Kore", idle_timeout_seconds=60, session_max_minutes=10),
        ),
    )
    async_session.add(connector)
    await async_session.commit()
    previous = configure_live_connector_preferences(SavedLiveConnectorPreferences())
    llm = AsyncMock()
    llm.ainvoke.return_value = AIMessage(
        content=json.dumps(
            {"intent": {"provider": "gemini", "settings": {"voice": "Kore"}}, "remove_fields": []}
        )
    )

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    try:
        with (
            installed_runtime_context(user_id=test_user.id, language="fr"),
            patch(
                "src.domains.agents.tools.application_live_connector_tools.get_db_context", session
            ),
            patch("src.domains.agents.application.command_service.get_db_context", session),
            patch("src.domains.agents.application.draft_editing.get_db_context", session),
            patch("src.domains.agents.services.hitl.draft_modifier.get_llm", return_value=llm),
        ):
            proposal = await update_lia_live_connector_settings_tool.coroutine(
                change={"provider": "gemini", "settings": {"voice": "Puck"}},
                runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore()),
            )
            item = next(iter(proposal.registry_updates.values()))
            original = ApplicationActionDraftContent.model_validate(item.payload["content"])
            edited = await DraftModificationService().modify(
                original.model_dump(mode="json"),
                "Choisis plutôt Kore",
                "application_action",
                user_language="fr",
                run_id=item.id,
            )
        revised = ApplicationActionDraftContent.model_validate(edited)
        command = await get_command(async_session, original.command_id, test_user.id)
        assert command is not None and matches_command(command, revised, item.id)
        assert not matches_command(command, original, item.id)
        assert revised.intent["live_connector_settings"]["settings"]["voice"] == "Kore"
        prompt = str(llm.ainvoke.call_args.args[0])
        assert "stored_digest" not in prompt and "private-secret-key" not in prompt
        await async_session.refresh(connector)
        assert connector.connector_metadata["models"]["model"]["voice"] == "Kore"
    finally:
        configure_live_connector_preferences(previous)
