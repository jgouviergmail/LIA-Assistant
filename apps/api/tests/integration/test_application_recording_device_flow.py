"""Original exact HITL, real ledger/session and one addressed browser continuation."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_device_snapshot import RecordingDeviceSnapshot
from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.recording_device_schemas import RecordingDeviceAck
from src.domains.agents.application.recording_device_service import (
    acknowledge_recording_device,
    claim_recording_device,
)
from src.domains.agents.effects.models import AgentEffect, EffectStatus
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_recording_device_tools
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize(
    "scenario", ["valid", "no_confirmation", "other_tab", "disabled", "bad_ack", "revoked"]
)
async def test_recording_device_uses_original_consent_and_never_replays(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "meetings_enabled", True)
    actor_id = test_user.id
    store = SessionStore(await get_redis_session())
    session = await store.create_session(str(actor_id))
    bound = bind_browser_session(actor_id, session.session_id, device_id=str(uuid4()))
    assert bound is not None
    origin = replace(
        bound,
        recording_snapshot=RecordingDeviceSnapshot(
            actor_id=actor_id,
            observed_at=datetime.now(UTC),
            supported=True,
            phase="idle",
            meeting_id=None,
        ),
    )

    @asynccontextmanager
    async def database() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", database)
    monkeypatch.setattr(application_recording_device_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    try:
        with installed_runtime_context(
            user_id=actor_id, application_origin=origin, deps=object(), execution_mode=mode
        ):
            proposal = await application_recording_device_tools.control_lia_meeting_recording_tool.coroutine(
                request={"action": "start"},
                runtime=make_tool_runtime(
                    user_id=actor_id,
                    application_origin=origin,
                    store=InMemoryStore(),
                    execution_mode=mode,
                ),
            )
            assert proposal.success and proposal.metadata["requires_confirmation"]
            item = next(iter(proposal.registry_updates.values()))
            content = item.payload["content"]
            command_id = content["command_id"]
            if scenario == "no_confirmation":
                with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                    await execute_application_action_draft(content, actor_id, object())
                return
            with patch.dict(draft_executor.EXECUTOR_REGISTRY):
                draft_executor.register_executor(
                    "application_action", execute_application_action_draft
                )
                result = await draft_executor._execute_confirmed_draft(
                    {
                        "draft_id": item.id,
                        "draft_type": "application_action",
                        "draft_content": content,
                    },
                    {"configurable": {"thread_id": f"recording-{mode}"}},
                    f"recording-{mode}",
                    "fr",
                )
            assert not result.success and result.result_data["phase"] == "waiting"
            if scenario == "disabled":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            if scenario == "revoked":
                await store.delete_session(session.session_id)
            if scenario in {"other_tab", "disabled", "revoked"}:
                candidate = (
                    replace(origin, device_id=uuid4()) if scenario == "other_tab" else origin
                )
                with pytest.raises(AuthorizationError):
                    await claim_recording_device(async_session, actor_id, command_id, candidate)
                await async_session.rollback()
                return
            claim = await claim_recording_device(async_session, actor_id, command_id, origin)
            assert claim is not None and claim.intent.action == "start"
            assert await claim_recording_device(async_session, actor_id, command_id, origin) is None
            ack = RecordingDeviceAck(
                claim_token=claim.claim_token,
                result="completed",
                phase="recording",
                meeting_id=uuid4(),
            )
            if scenario == "bad_ack":
                with pytest.raises(AuthorizationError):
                    await acknowledge_recording_device(
                        async_session,
                        actor_id,
                        command_id,
                        ack.model_copy(update={"phase": "processing"}),
                        origin,
                    )
                await async_session.rollback()
            outcome = await acknowledge_recording_device(
                async_session, actor_id, command_id, ack, origin
            )
            assert outcome.success and outcome.values["device_reported"] is True
            assert outcome.values["processing_completed"] is False
            with pytest.raises(AuthorizationError):
                await acknowledge_recording_device(async_session, actor_id, command_id, ack, origin)
            await async_session.rollback()
            effects = (
                await async_session.scalars(
                    select(AgentEffect).where(AgentEffect.user_id == actor_id)
                )
            ).all()
            assert sum(effect.status == EffectStatus.WAITING for effect in effects) == 1
            assert sum(effect.status == EffectStatus.SUCCEEDED for effect in effects) == 1
    finally:
        await async_session.rollback()
        await store.delete_session(session.session_id)
