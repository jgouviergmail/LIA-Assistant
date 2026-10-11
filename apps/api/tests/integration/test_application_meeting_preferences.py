"""Original UI and exact HITL share preference CAS and owner transaction."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_meeting_preference_tools import (
    update_lia_meeting_preferences_tool,
)
from src.domains.meetings.preference_commands import replace_meeting_preferences
from src.domains.meetings.preference_gateway import SavedMeetingPreferences
from src.domains.meetings.repository import MeetingPreferenceRepository
from src.domains.meetings.schemas import MeetingPreferencesUpdate
from src.domains.users.models import User
from src.infrastructure.meeting_preferences import configure_meeting_preferences
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention",
    ["none", "manual_change", "platform_off", "meetings_off", "ceiling_change", "no_op", "clamped"],
)
async def test_confirmed_defaults_preserve_unrequested_fields_and_refuse_changed_facts(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "meetings_enabled", True)
    monkeypatch.setattr(settings, "meetings_audio_retention_hours_max", 24)
    original = MeetingPreferencesUpdate(
        stt_engine="auto",
        language="fr",
        auto_email=False,
        keep_audio_hours=0,
        default_template_ref=None,
    )
    await replace_meeting_preferences(async_session, test_user.id, original, "fr")
    actor_id = test_user.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    previous = configure_meeting_preferences(SavedMeetingPreferences())
    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    queue: asyncio.Queue[ChatStreamChunk] = asyncio.Queue()
    try:
        with (
            installed_runtime_context(
                user_id=actor_id, language="fr", deps=object(), side_channel_queue=queue
            ),
            patch(
                "src.domains.agents.tools.application_meeting_preference_tools.get_db_context",
                session,
            ),
            patch("src.domains.agents.application.command_service.get_db_context", session),
            patch("src.domains.agents.application.draft_execution.get_db_context", session),
            patch("src.domains.agents.effects.runtime._LEDGER", ledger),
            patch.dict(draft_executor.EXECUTOR_REGISTRY),
        ):
            requested = (
                {"keep_audio_hours": 999}
                if intervention == "clamped"
                else {"auto_email": intervention != "no_op"}
            )
            proposal = await update_lia_meeting_preferences_tool.coroutine(
                request=requested,
                runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
            )
            assert proposal.success and proposal.metadata["requires_confirmation"]
            item = next(iter(proposal.registry_updates.values()))
            before = await MeetingPreferenceRepository(async_session).get_for_user(actor_id)
            assert (
                before is not None and before.auto_email is False and before.keep_audio_hours == 0
            )
            if intervention == "manual_change":
                await replace_meeting_preferences(
                    async_session, actor_id, original.model_copy(update={"language": "de"}), "fr"
                )
            if intervention == "platform_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            if intervention == "meetings_off":
                monkeypatch.setattr(settings, "meetings_enabled", False)
            if intervention == "ceiling_change":
                monkeypatch.setattr(settings, "meetings_audio_retention_hours_max", 12)
            draft_executor.register_executor("application_action", execute_application_action_draft)
            outcome = await draft_executor._execute_confirmed_draft(
                {
                    "draft_id": item.id,
                    "draft_type": "application_action",
                    "draft_content": item.payload["content"],
                },
                {"configurable": {"thread_id": "meeting-settings"}},
                "meeting-settings",
                "fr",
            )
    finally:
        configure_meeting_preferences(previous)
    assert outcome.success is (intervention in {"none", "no_op", "clamped"})
    saved = await MeetingPreferenceRepository(async_session).get_for_user(actor_id)
    assert saved is not None
    assert saved.language == ("de" if intervention == "manual_change" else "fr")
    assert saved.auto_email is (intervention == "none")
    assert saved.keep_audio_hours == (24 if intervention == "clamped" else 0)
    if intervention in {"manual_change", "ceiling_change"}:
        assert outcome.error == "STALE_STATE"
    if intervention in {"platform_off", "meetings_off"}:
        assert outcome.error == "CAPABILITY_DISABLED"
        ledger.claim.assert_not_awaited()
    hints = [queue.get_nowait() for _ in range(queue.qsize())]
    hints = [event for event in hints if event.type == "application_state_changed"]
    assert len(hints) == int(intervention in {"none", "clamped"})
    if hints:
        assert hints[0].metadata["change"]["resources"] == ["meeting_preferences"]
        assert hints[0].metadata["change"]["changed_fields"] == ["meeting_preferences"]
        assert "language" not in str(hints[0].metadata)
